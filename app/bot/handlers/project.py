from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.db.models import User, ProjectStatus, ImageType
from app.db.session import AsyncSessionLocal
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.bot.states.states import ProjectForm
from app.bot.messages import (
    NEW_PROJECT_START, ASK_ROOM_TYPE, ASK_AREA, AREA_INVALID,
    ASK_CEILING, CEILING_INVALID, ASK_STYLE, ASK_BUDGET,
    ASK_FREE_SPACE, ASK_KEEP, ASK_REMOVE, ASK_EXTRA,
    ASK_PHOTOS, PHOTO_RECEIVED, PHOTO_TOO_LARGE, PHOTO_BAD_QUALITY,
    PHOTO_MAX_REACHED, CONFIRMATION_TEMPLATE,
    ROOM_TYPE_LABELS, STYLE_LABELS, BUDGET_LABELS,
    ERROR_GENERAL,
)
from app.bot.keyboards.keyboards import (
    room_type_keyboard, style_keyboard, budget_keyboard,
    free_space_keyboard, skip_keyboard, photos_done_keyboard,
    confirmation_keyboard, remove_keyboard,
)
from app.core.config import settings
from app.integrations.storage.s3 import storage_service

router = Router(name="project")


# ─── Start project ────────────────────────────────────────────────────────────

@router.message(Command("new"))
@router.message(F.text == "🏠 Создать проект")
async def cmd_new_project(message: Message, state: FSMContext, db_user: User):
    # Check active project limit
    async with AsyncSessionLocal() as session:
        repo = ProjectRepository(session)
        active = await repo.count_active_projects(db_user.id)

    if active >= settings.max_active_projects:
        await message.answer(
            f"⚠️ У тебя уже {active} активных проекта(ов). "
            f"Завершите или отмените их прежде чем создавать новый."
        )
        return

    # Create draft project in DB
    async with AsyncSessionLocal() as session:
        repo = ProjectRepository(session)
        project = await repo.create(db_user.id)
        await session.commit()
        project_id = project.id

    await state.clear()
    await state.update_data(project_id=project_id, photo_count=0)

    await message.answer(NEW_PROJECT_START, parse_mode="HTML", reply_markup=remove_keyboard())
    await message.answer(ASK_ROOM_TYPE, reply_markup=room_type_keyboard())
    await state.set_state(ProjectForm.room_type)


# ─── Room type ────────────────────────────────────────────────────────────────

@router.callback_query(ProjectForm.room_type, F.data.startswith("room:"))
async def cb_room_type(call: CallbackQuery, state: FSMContext):
    value = call.data.split(":", 1)[1]
    await state.update_data(room_type=value)

    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        repo = ProjectRepository(session)
        await repo.update_params(data["project_id"], room_type=value)
        await session.commit()

    await call.message.edit_reply_markup()
    await call.message.answer(ASK_AREA)
    await state.set_state(ProjectForm.area)
    await call.answer()


# ─── Area ─────────────────────────────────────────────────────────────────────

@router.message(ProjectForm.area)
async def msg_area(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        area = float(text)
        if not (3 <= area <= 200):
            raise ValueError
    except ValueError:
        await message.answer(AREA_INVALID)
        return

    await state.update_data(area_m2=area)
    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        await ProjectRepository(session).update_params(data["project_id"], area_m2=area)
        await session.commit()

    await message.answer(ASK_CEILING, reply_markup=skip_keyboard("ceiling"))
    await state.set_state(ProjectForm.ceiling_height)


# ─── Ceiling height (optional) ────────────────────────────────────────────────

@router.callback_query(ProjectForm.ceiling_height, F.data == "skip:ceiling")
async def cb_skip_ceiling(call: CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup()
    await call.message.answer(ASK_STYLE, reply_markup=style_keyboard())
    await state.set_state(ProjectForm.style)
    await call.answer()


@router.message(ProjectForm.ceiling_height)
async def msg_ceiling(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        height = float(text)
        if not (1.8 <= height <= 6.0):
            raise ValueError
    except ValueError:
        await message.answer(CEILING_INVALID)
        return

    await state.update_data(ceiling_height=height)
    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        await ProjectRepository(session).update_params(data["project_id"], ceiling_height=height)
        await session.commit()

    await message.answer(ASK_STYLE, reply_markup=style_keyboard())
    await state.set_state(ProjectForm.style)


# ─── Style ────────────────────────────────────────────────────────────────────

@router.callback_query(ProjectForm.style, F.data.startswith("style:"))
async def cb_style(call: CallbackQuery, state: FSMContext):
    value = call.data.split(":", 1)[1]
    await state.update_data(style=value)

    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        await ProjectRepository(session).update_params(data["project_id"], style=value)
        await session.commit()

    await call.message.edit_reply_markup()
    await call.message.answer(ASK_BUDGET, reply_markup=budget_keyboard())
    await state.set_state(ProjectForm.budget)
    await call.answer()


# ─── Budget ───────────────────────────────────────────────────────────────────

@router.callback_query(ProjectForm.budget, F.data.startswith("budget:"))
async def cb_budget(call: CallbackQuery, state: FSMContext):
    value = call.data.split(":", 1)[1]
    await state.update_data(budget_tier=value)

    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        await ProjectRepository(session).update_params(data["project_id"], budget_tier=value)
        await session.commit()

    await call.message.edit_reply_markup()
    await call.message.answer(ASK_FREE_SPACE, reply_markup=free_space_keyboard())
    await state.set_state(ProjectForm.free_space)
    await call.answer()


# ─── Free space ───────────────────────────────────────────────────────────────

@router.callback_query(ProjectForm.free_space, F.data.startswith("space:"))
async def cb_free_space(call: CallbackQuery, state: FSMContext):
    value = call.data.split(":", 1)[1]
    await state.update_data(free_space_percent=value)

    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        await ProjectRepository(session).update_params(
            data["project_id"], free_space_percent=value
        )
        await session.commit()

    await call.message.edit_reply_markup()
    await call.message.answer(ASK_KEEP, reply_markup=skip_keyboard("keep"))
    await state.set_state(ProjectForm.keep_items)
    await call.answer()


# ─── Keep items (optional) ────────────────────────────────────────────────────

@router.callback_query(ProjectForm.keep_items, F.data == "skip:keep")
async def cb_skip_keep(call: CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup()
    await call.message.answer(ASK_REMOVE, reply_markup=skip_keyboard("remove"))
    await state.set_state(ProjectForm.remove_items)
    await call.answer()


@router.message(ProjectForm.keep_items)
async def msg_keep(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.update_data(keep_items=text)

    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        await ProjectRepository(session).update_params(data["project_id"], keep_items=text)
        await session.commit()

    await message.answer(ASK_REMOVE, reply_markup=skip_keyboard("remove"))
    await state.set_state(ProjectForm.remove_items)


# ─── Remove items (optional) ──────────────────────────────────────────────────

@router.callback_query(ProjectForm.remove_items, F.data == "skip:remove")
async def cb_skip_remove(call: CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup()
    await call.message.answer(ASK_EXTRA, reply_markup=skip_keyboard("extra"))
    await state.set_state(ProjectForm.extra_notes)
    await call.answer()


@router.message(ProjectForm.remove_items)
async def msg_remove(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.update_data(remove_items=text)

    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        await ProjectRepository(session).update_params(data["project_id"], remove_items=text)
        await session.commit()

    await message.answer(ASK_EXTRA, reply_markup=skip_keyboard("extra"))
    await state.set_state(ProjectForm.extra_notes)


# ─── Extra notes (optional) ───────────────────────────────────────────────────

@router.callback_query(ProjectForm.extra_notes, F.data == "skip:extra")
async def cb_skip_extra(call: CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup()
    await call.message.answer(ASK_PHOTOS, reply_markup=photos_done_keyboard())
    await state.set_state(ProjectForm.photos)
    await call.answer()


@router.message(ProjectForm.extra_notes)
async def msg_extra(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.update_data(extra_notes=text)

    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        await ProjectRepository(session).update_params(data["project_id"], extra_notes=text)
        await session.commit()

    await message.answer(ASK_PHOTOS, reply_markup=photos_done_keyboard())
    await state.set_state(ProjectForm.photos)


# ─── Photos ───────────────────────────────────────────────────────────────────

@router.message(ProjectForm.photos, F.photo)
async def msg_photo(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    photo_count = data.get("photo_count", 0)
    project_id = data["project_id"]

    if photo_count >= 3:
        await message.answer(PHOTO_MAX_REACHED)
        return

    # Get best quality photo
    photo: PhotoSize = message.photo[-1]

    # Check file size
    if photo.file_size and photo.file_size > settings.max_photo_size_bytes:
        await message.answer(PHOTO_TOO_LARGE.format(max_mb=settings.max_photo_size_mb))
        return

    try:
        # Download photo bytes
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        raw_bytes = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)

        # Upload to storage
        storage_path = storage_service.upload_bytes(
            data=raw_bytes,
            prefix=f"inputs/{project_id}",
            extension="jpg",
        )

        # Save reference in DB
        async with AsyncSessionLocal() as session:
            await ProjectRepository(session).add_image(
                project_id=project_id,
                image_type=ImageType.INPUT,
                file_path=storage_path,
                file_id_telegram=photo.file_id,
                sort_order=photo_count,
            )
            await session.commit()

        photo_count += 1
        await state.update_data(photo_count=photo_count)

        # Quality warning for very small photos
        if photo.width and photo.height and (photo.width < 600 or photo.height < 600):
            await message.answer(PHOTO_BAD_QUALITY)

        if photo_count >= 3:
            await message.answer(
                f"✅ Фото {photo_count}/3 получено. Максимум достигнут.",
                reply_markup=photos_done_keyboard(),
            )
        else:
            await message.answer(
                PHOTO_RECEIVED.format(count=photo_count),
                reply_markup=photos_done_keyboard(),
            )

    except Exception as e:
        logger.error(f"Photo upload failed for project {project_id}: {e}")
        await message.answer(ERROR_GENERAL)


@router.callback_query(ProjectForm.photos, F.data == "photos:done")
async def cb_photos_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("photo_count", 0) == 0:
        await call.answer("⚠️ Нужно загрузить хотя бы 1 фото!", show_alert=True)
        return

    await call.message.edit_reply_markup()
    await _show_confirmation(call.message, state, data)
    await state.set_state(ProjectForm.confirmation)
    await call.answer()


# ─── Confirmation ─────────────────────────────────────────────────────────────

async def _show_confirmation(message: Message, state: FSMContext, data: dict):
    text = CONFIRMATION_TEMPLATE.format(
        room_type=ROOM_TYPE_LABELS.get(data.get("room_type", ""), "—"),
        area=_fmt(data.get("area_m2")),
        ceiling=_fmt(data.get("ceiling_height")),
        style=STYLE_LABELS.get(data.get("style", ""), "—"),
        budget=BUDGET_LABELS.get(data.get("budget_tier", ""), "—"),
        free_space=_fmt(data.get("free_space_percent")),
        keep=_fmt(data.get("keep_items")),
        remove=_fmt(data.get("remove_items")),
        extra=_fmt(data.get("extra_notes")),
        photos_count=data.get("photo_count", 0),
    )
    await message.answer(text, parse_mode="HTML", reply_markup=confirmation_keyboard())


@router.callback_query(ProjectForm.confirmation, F.data == "confirm:edit")
async def cb_confirm_edit(call: CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup()
    await call.message.answer(ASK_ROOM_TYPE, reply_markup=room_type_keyboard())
    await state.set_state(ProjectForm.room_type)
    await call.answer()


@router.callback_query(F.data == "project:cancel")
async def cb_cancel_project(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    project_id = data.get("project_id")

    if project_id:
        async with AsyncSessionLocal() as session:
            await ProjectRepository(session).set_status(project_id, ProjectStatus.CANCELLED)
            await session.commit()

    await state.clear()
    await call.message.edit_reply_markup()
    await call.message.answer("❌ Проект отменён.")
    await call.answer()


@router.callback_query(ProjectForm.confirmation, F.data == "confirm:start")
async def cb_confirm_start(call: CallbackQuery, state: FSMContext, db_user: User):
    data = await state.get_data()
    project_id = data["project_id"]

    await call.message.edit_reply_markup()
    await state.clear()

    # Check free preview availability
    from app.core.config import settings as cfg
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(db_user.id)
        free_used = user.free_previews_used if user else 0

    can_free = free_used < cfg.free_previews_limit

    if can_free:
        # Offer tariff selection
        from app.bot.keyboards.keyboards import tariff_keyboard
        from app.bot.messages import TARIFF_SELECTION
        await call.message.answer(
            TARIFF_SELECTION, parse_mode="HTML", reply_markup=tariff_keyboard()
        )
    else:
        from app.bot.messages import FREE_LIMIT_REACHED
        from app.bot.keyboards.keyboards import tariff_keyboard
        await call.message.answer(
            FREE_LIMIT_REACHED, parse_mode="HTML", reply_markup=tariff_keyboard()
        )

    # Store project_id for payment handler
    from app.bot.states.states import PaymentFlow
    await state.set_state(PaymentFlow.tariff_selection)
    await state.update_data(project_id=project_id)
    await call.answer()


def _fmt(value, fallback="—"):
    if value is None:
        return fallback
    return str(value)
