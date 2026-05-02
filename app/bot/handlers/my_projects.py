from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.db.models import User, ProjectStatus
from app.db.session import AsyncSessionLocal
from app.repositories.project_repository import ProjectRepository
from app.bot.messages import (
    NO_PROJECTS, MY_PROJECTS_HEADER,
    ROOM_TYPE_LABELS, STYLE_LABELS, STATUS_LABELS, ERROR_GENERAL,
)
from app.bot.keyboards.keyboards import project_actions_keyboard, main_menu_keyboard
from app.services.generation.service import GenerationService
from app.integrations.storage.s3 import storage_service
from aiogram.types import BufferedInputFile

router = Router(name="my_projects")


@router.message(Command("myprojects"))
@router.message(F.text == "📁 Мои проекты")
async def cmd_my_projects(message: Message, db_user: User):
    async with AsyncSessionLocal() as session:
        repo = ProjectRepository(session)
        projects = await repo.get_user_projects(db_user.id, limit=10)

    if not projects:
        await message.answer(NO_PROJECTS, reply_markup=main_menu_keyboard())
        return

    await message.answer(MY_PROJECTS_HEADER, parse_mode="HTML")

    for project in projects:
        room = ROOM_TYPE_LABELS.get(project.room_type or "", "—")
        style = STYLE_LABELS.get(project.style or "", "—")
        status = STATUS_LABELS.get(project.status, project.status)
        date = project.created_at.strftime("%d.%m.%Y")

        text = (
            f"<b>#{project.id}</b> | {room} | {style}\n"
            f"📅 {date} | {status}"
        )
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=project_actions_keyboard(project.id, project.status),
        )


# ─── Project actions ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("proj_view:"))
async def cb_view_project(call: CallbackQuery):
    project_id = int(call.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        repo = ProjectRepository(session)
        project = await repo.get_by_id(project_id)

    if not project or project.status != ProjectStatus.DONE:
        await call.answer("Результат пока недоступен.", show_alert=True)
        return

    output_images = project.output_images
    if not output_images:
        await call.answer("Изображения не найдены.", show_alert=True)
        return

    await call.answer()

    for img_record in sorted(output_images, key=lambda x: x.sort_order):
        try:
            img_bytes = storage_service.download_bytes(img_record.file_path)
            photo = BufferedInputFile(img_bytes, filename="interior.jpg")
            await call.message.answer_photo(photo)
        except Exception:
            pass

    if project.concept_text:
        await call.message.answer(project.concept_text, parse_mode="HTML")


@router.callback_query(F.data.startswith("proj_retry:"))
async def cb_retry_project(call: CallbackQuery, db_user: User):
    project_id = int(call.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        service = GenerationService(session)
        try:
            await service.enqueue(project_id)
            await call.answer("🔄 Генерация запущена заново!")
        except Exception:
            await call.answer("❌ Ошибка запуска", show_alert=True)


@router.callback_query(F.data.startswith("proj_delete:"))
async def cb_delete_project(call: CallbackQuery, db_user: User):
    project_id = int(call.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        repo = ProjectRepository(session)
        project = await repo.get_by_id(project_id)

        if not project or project.user_id != db_user.id:
            await call.answer("Проект не найден.", show_alert=True)
            return

        await repo.delete(project_id)
        await session.commit()

    await call.message.edit_reply_markup()
    await call.message.answer(f"🗑 Проект #{project_id} удалён.")
    await call.answer()


# ─── Post-result action buttons ───────────────────────────────────────────────

@router.callback_query(F.data == "result:new_project")
async def cb_result_new_project(call: CallbackQuery, state: FSMContext, db_user: User):
    await call.message.answer("Создаём новый проект...")
    await call.answer()
    # Reuse the new project command
    from app.bot.handlers.project import cmd_new_project
    await cmd_new_project(call.message, state, db_user)


@router.callback_query(F.data == "result:my_projects")
async def cb_result_my_projects(call: CallbackQuery, db_user: User):
    await call.answer()
    await cmd_my_projects(call.message, db_user)


@router.callback_query(F.data == "result:upgrade")
async def cb_result_upgrade(call: CallbackQuery):
    from app.bot.messages import TARIFF_SELECTION
    from app.bot.keyboards.keyboards import tariff_keyboard
    await call.message.answer(TARIFF_SELECTION, parse_mode="HTML", reply_markup=tariff_keyboard())
    await call.answer()
