from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message, LabeledPrice,
    PreCheckoutQuery, SuccessfulPayment,
)
from loguru import logger

from app.bot.states.states import PaymentFlow
from app.db.models import Tariff, PaymentStatus, ProjectStatus
from app.db.session import AsyncSessionLocal
from app.repositories.project_repository import ProjectRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.user_repository import UserRepository
from app.services.generation.service import GenerationService
from app.core.config import settings
from app.bot.messages import (
    PAYMENT_SUCCESS, PAYMENT_FAILED, PAYMENT_CANCELLED,
    GENERATION_ANALYZING,
)
from app.bot.keyboards.keyboards import main_menu_keyboard

router = Router(name="payment")

TARIFF_PRICES = {
    Tariff.FREE: 0,
    Tariff.ROOM: settings.price_room,
    Tariff.PRO_ROOM: settings.price_pro_room,
    Tariff.FLAT: settings.price_flat,
    Tariff.REALTOR_PACK: settings.price_realtor_pack,
}

TARIFF_LABELS = {
    Tariff.FREE: "🆓 Бесплатный preview",
    Tariff.ROOM: "🏠 Room",
    Tariff.PRO_ROOM: "⭐ Pro Room",
    Tariff.FLAT: "🏢 Flat",
    Tariff.REALTOR_PACK: "🏷 Realtor Pack",
}


@router.callback_query(PaymentFlow.tariff_selection, F.data.startswith("tariff:"))
async def cb_tariff_selected(call: CallbackQuery, state: FSMContext, bot: Bot, db_user):
    from aiogram.fsm.context import FSMContext
    tariff_str = call.data.split(":", 1)[1]

    try:
        tariff = Tariff(tariff_str)
    except ValueError:
        await call.answer("Неверный тариф", show_alert=True)
        return

    data = await state.get_data()
    project_id = data.get("project_id")

    if not project_id:
        await call.answer("Ошибка: проект не найден", show_alert=True)
        return

    await call.message.edit_reply_markup()

    # Update tariff on project
    async with AsyncSessionLocal() as session:
        await ProjectRepository(session).update_params(project_id, tariff=tariff.value)
        await session.commit()

    if tariff == Tariff.FREE:
        await _launch_free(call, state, project_id, db_user)
    else:
        await _start_payment(call, state, bot, project_id, tariff, db_user)

    await call.answer()


async def _launch_free(call: CallbackQuery, state, project_id: int, db_user):
    """Launch free tier generation immediately."""
    await call.message.answer("🆓 Запускаю бесплатный preview...")
    await call.message.answer(GENERATION_ANALYZING)
    await state.clear()

    async with AsyncSessionLocal() as session:
        # Increment free usage counter
        await UserRepository(session).increment_free_previews(db_user.id)
        await session.commit()

    async with AsyncSessionLocal() as session:
        service = GenerationService(session)
        try:
            await service.enqueue(project_id)
        except Exception as e:
            logger.error(f"Failed to enqueue generation for project {project_id}: {e}")
            await call.message.answer("❌ Ошибка запуска генерации. Попробуй позже.")


async def _start_payment(call: CallbackQuery, state, bot: Bot, project_id: int, tariff: Tariff, db_user):
    """Send Telegram payment invoice."""
    amount = TARIFF_PRICES[tariff]
    label = TARIFF_LABELS[tariff]

    # Create payment record
    async with AsyncSessionLocal() as session:
        payment = await PaymentRepository(session).create(
            project_id=project_id,
            user_id=db_user.id,
            tariff=tariff,
            amount=amount,
        )
        await session.commit()
        payment_id = payment.id

    await state.update_data(payment_id=payment_id)
    await state.set_state(PaymentFlow.waiting_payment)

    try:
        await bot.send_invoice(
            chat_id=call.from_user.id,
            title=f"Тариф {label}",
            description=f"AI-визуализация интерьера — {label}",
            payload=f"project:{project_id}:payment:{payment_id}",
            provider_token=settings.payment_token,
            currency="RUB",
            prices=[LabeledPrice(label=label, amount=amount)],
            start_parameter=f"pay_{project_id}",
        )
    except Exception as e:
        logger.error(f"Failed to send invoice: {e}")
        await call.message.answer(PAYMENT_FAILED)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    """Always approve pre-checkout."""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, state: FSMContext):
    payment_data = message.successful_payment
    payload = payment_data.invoice_payload  # "project:{id}:payment:{id}"

    try:
        parts = payload.split(":")
        project_id = int(parts[1])
        payment_id = int(parts[3])
    except (IndexError, ValueError) as e:
        logger.error(f"Invalid payment payload: {payload} — {e}")
        await message.answer(PAYMENT_FAILED)
        return

    external_id = payment_data.telegram_payment_charge_id

    async with AsyncSessionLocal() as session:
        payment_repo = PaymentRepository(session)
        project_repo = ProjectRepository(session)

        await payment_repo.set_status(
            payment_id, PaymentStatus.SUCCEEDED, external_payment_id=external_id
        )
        await project_repo.set_status(project_id, ProjectStatus.QUEUED)
        await session.commit()

    await message.answer(PAYMENT_SUCCESS, reply_markup=main_menu_keyboard())
    await message.answer(GENERATION_ANALYZING)
    await state.clear()

    # Enqueue generation
    async with AsyncSessionLocal() as session:
        service = GenerationService(session)
        try:
            await service.enqueue(project_id)
        except Exception as e:
            logger.error(f"Failed to enqueue after payment for project {project_id}: {e}")
            await message.answer("❌ Ошибка запуска генерации. Наша команда уже оповещена.")


@router.callback_query(F.data == "payment:cancel")
async def cb_payment_cancel(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    payment_id = data.get("payment_id")

    if payment_id:
        async with AsyncSessionLocal() as session:
            await PaymentRepository(session).set_status(payment_id, PaymentStatus.CANCELLED)
            await session.commit()

    await state.clear()
    await call.message.edit_reply_markup()
    await call.message.answer(PAYMENT_CANCELLED, reply_markup=main_menu_keyboard())
    await call.answer()


# Import needed for type hint inside function
from aiogram.fsm.context import FSMContext  # noqa: E402 (already imported by aiogram)
