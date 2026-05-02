from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.core.config import settings
from app.db.models import ProjectStatus, ActorType
from app.db.session import AsyncSessionLocal
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.services.generation.service import GenerationService
from app.services.notification.service import NotificationService
from app.bot.states.states import AdminFlow
from app.bot.messages import ROOM_TYPE_LABELS, STYLE_LABELS, STATUS_LABELS
from app.bot.keyboards.keyboards import admin_project_keyboard

router = Router(name="admin")


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def admin_only(func):
    """Decorator to restrict handler to admins."""
    import functools

    @functools.wraps(func)
    async def wrapper(event, *args, **kwargs):
        uid = event.from_user.id if hasattr(event, "from_user") else 0
        if not is_admin(uid):
            if hasattr(event, "answer"):
                await event.answer("🚫 Нет доступа.")
            return
        return await func(event, *args, **kwargs)

    return wrapper


# ─── /admin ───────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message):
    await message.answer(
        "🔧 <b>Admin Panel</b>\n\n"
        "Команды:\n"
        "/projects — последние проекты\n"
        "/stats — статистика\n"
        "/broadcast — рассылка\n"
        "/project &lt;id&gt; — детали проекта\n"
        "/retry &lt;id&gt; — перезапустить генерацию\n",
        parse_mode="HTML",
    )


# ─── /projects ────────────────────────────────────────────────────────────────

@router.message(Command("projects"))
@admin_only
async def cmd_projects(message: Message):
    args = message.text.split()
    status_filter = args[1] if len(args) > 1 else None

    async with AsyncSessionLocal() as session:
        repo = ProjectRepository(session)
        projects = await repo.list_all(status=status_filter, limit=20)

    if not projects:
        await message.answer("Проектов не найдено.")
        return

    lines = [f"📋 <b>Проекты</b> ({len(projects)}):\n"]
    for p in projects:
        status = STATUS_LABELS.get(p.status, p.status)
        user_info = f"@{p.user.username}" if p.user and p.user.username else f"id={p.user_id}"
        room = ROOM_TYPE_LABELS.get(p.room_type or "", "—")
        lines.append(f"<b>#{p.id}</b> {room} | {status} | {user_info}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── /project <id> ────────────────────────────────────────────────────────────

@router.message(Command("project"))
@admin_only
async def cmd_project_detail(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /project <id>")
        return

    try:
        project_id = int(args[1])
    except ValueError:
        await message.answer("⚠️ ID должен быть числом.")
        return

    async with AsyncSessionLocal() as session:
        project = await ProjectRepository(session).get_by_id(project_id)

    if not project:
        await message.answer(f"Проект #{project_id} не найден.")
        return

    status = STATUS_LABELS.get(project.status, project.status)
    room = ROOM_TYPE_LABELS.get(project.room_type or "", "—")
    style = STYLE_LABELS.get(project.style or "", "—")
    user_info = (
        f"@{project.user.username}" if project.user and project.user.username
        else f"tg_id={project.user.telegram_id if project.user else '?'}"
    )

    text = (
        f"📁 <b>Проект #{project.id}</b>\n\n"
        f"👤 Пользователь: {user_info}\n"
        f"🏠 Тип: {room}\n"
        f"📐 Площадь: {project.area_m2 or '—'} м²\n"
        f"🎨 Стиль: {style}\n"
        f"💰 Бюджет: {project.budget_tier or '—'}\n"
        f"📦 Тариф: {project.tariff}\n"
        f"📊 Статус: {status}\n"
        f"📸 Фото: {len(project.input_photos)} вход / {len(project.output_images)} выход\n"
        f"📅 Создан: {project.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=admin_project_keyboard(project.id),
    )


# ─── /retry <id> ─────────────────────────────────────────────────────────────

@router.message(Command("retry"))
@admin_only
async def cmd_retry(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /retry <id>")
        return

    try:
        project_id = int(args[1])
    except ValueError:
        await message.answer("⚠️ ID должен быть числом.")
        return

    async with AsyncSessionLocal() as session:
        service = GenerationService(session)
        try:
            await service.enqueue(project_id)
            await message.answer(f"✅ Генерация проекта #{project_id} запущена.")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")


# ─── /stats ───────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
@admin_only
async def cmd_stats(message: Message):
    async with AsyncSessionLocal() as session:
        project_repo = ProjectRepository(session)
        user_repo = UserRepository(session)

        status_counts = await project_repo.count_by_status()
        users = await user_repo.list_all(limit=1000)

    total_users = len(users)
    blocked = sum(1 for u in users if u.is_blocked)
    total_projects = sum(status_counts.values())
    done = status_counts.get(ProjectStatus.DONE, 0)
    failed = status_counts.get(ProjectStatus.FAILED, 0)

    lines = [
        "📊 <b>Статистика</b>\n",
        f"👥 Пользователей: {total_users} (заблокировано: {blocked})",
        f"📁 Проектов всего: {total_projects}",
        f"✅ Завершено: {done}",
        f"❌ Ошибок: {failed}",
        "",
        "<b>По статусам:</b>",
    ]
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        label = STATUS_LABELS.get(status, status)
        lines.append(f"  {label}: {count}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── /broadcast ──────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
@admin_only
async def cmd_broadcast_start(message: Message, state: FSMContext):
    await message.answer(
        "📢 Введи текст рассылки (поддерживается HTML).\n"
        "Для отмены — /cancel"
    )
    await state.set_state(AdminFlow.waiting_broadcast_text)


@router.message(AdminFlow.waiting_broadcast_text)
@admin_only
async def cmd_broadcast_send(message: Message, state: FSMContext):
    text = message.text or message.caption or ""
    if not text:
        await message.answer("⚠️ Текст не может быть пустым.")
        return

    await state.clear()
    await message.answer("📤 Начинаю рассылку...")

    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).list_all(limit=10000)

    user_ids = [u.telegram_id for u in users if not u.is_blocked]

    notifier = NotificationService()
    result = await notifier.broadcast(text, user_ids)

    await message.answer(
        f"✅ Рассылка завершена.\n"
        f"Отправлено: {result['sent']}, ошибок: {result['failed']}"
    )


# ─── Inline admin buttons ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_retry:"))
@admin_only
async def cb_admin_retry(call: CallbackQuery):
    project_id = int(call.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        service = GenerationService(session)
        try:
            await service.enqueue(project_id)
            await call.answer(f"✅ Генерация #{project_id} запущена")
        except Exception as e:
            await call.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("admin_done:"))
@admin_only
async def cb_admin_done(call: CallbackQuery):
    project_id = int(call.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await ProjectRepository(session).set_status(project_id, ProjectStatus.DONE)
        await session.commit()
    await call.answer(f"✅ Проект #{project_id} помечен как готовый")
    await call.message.edit_reply_markup()


@router.callback_query(F.data.startswith("admin_cancel:"))
@admin_only
async def cb_admin_cancel(call: CallbackQuery):
    project_id = int(call.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await ProjectRepository(session).set_status(project_id, ProjectStatus.CANCELLED)
        await session.commit()
    await call.answer(f"❌ Проект #{project_id} отменён")
    await call.message.edit_reply_markup()
