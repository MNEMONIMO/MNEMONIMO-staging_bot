"""Unit tests for the payment-flow handlers (ТЗ §12)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers import payment as payment_module
from app.db.models import PaymentStatus, ProjectStatus, Tariff


# ─── TARIFF tables ────────────────────────────────────────────────────────────

def test_tariff_prices_cover_every_enum_value():
    """Every Tariff must have a price (FREE = 0) so /buy never crashes."""
    for tariff in Tariff:
        assert tariff in payment_module.TARIFF_PRICES
        assert payment_module.TARIFF_PRICES[tariff] >= 0
    assert payment_module.TARIFF_PRICES[Tariff.FREE] == 0


def test_tariff_labels_cover_every_enum_value():
    for tariff in Tariff:
        assert tariff in payment_module.TARIFF_LABELS
        assert payment_module.TARIFF_LABELS[tariff].strip() != ""


def test_paid_tariffs_strictly_more_expensive_than_free():
    for tariff in Tariff:
        if tariff == Tariff.FREE:
            continue
        assert payment_module.TARIFF_PRICES[tariff] > 0


# ─── successful_payment payload parser ────────────────────────────────────────

@pytest.mark.asyncio
async def test_successful_payment_parses_valid_payload(monkeypatch):
    """Happy path: payload `project:42:payment:7` flips both records."""

    payment_repo = MagicMock()
    payment_repo.set_status = AsyncMock()
    project_repo = MagicMock()
    project_repo.set_status = AsyncMock()

    @asynccontextmanager
    async def fake_session_local():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    monkeypatch.setattr(payment_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(payment_module, "PaymentRepository", lambda s: payment_repo)
    monkeypatch.setattr(payment_module, "ProjectRepository", lambda s: project_repo)

    enqueue = AsyncMock()
    monkeypatch.setattr(
        payment_module, "GenerationService",
        lambda s: SimpleNamespace(enqueue=enqueue),
    )

    state = MagicMock()
    state.clear = AsyncMock()

    message = MagicMock()
    message.answer = AsyncMock()
    message.successful_payment = SimpleNamespace(
        invoice_payload="project:42:payment:7",
        telegram_payment_charge_id="tg-charge-xyz",
    )

    await payment_module.successful_payment(message, state)

    payment_repo.set_status.assert_awaited_once_with(
        7, PaymentStatus.SUCCEEDED, external_payment_id="tg-charge-xyz"
    )
    project_repo.set_status.assert_awaited_once_with(42, ProjectStatus.QUEUED)
    enqueue.assert_awaited_once_with(42)
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_payload", [
    "garbage",
    "project:abc:payment:7",
    "project:42:payment:notnum",
    "",
    "project:42",
])
async def test_successful_payment_handles_malformed_payload(monkeypatch, bad_payload):
    """Bad payload must NOT raise — user gets PAYMENT_FAILED instead."""

    monkeypatch.setattr(payment_module, "AsyncSessionLocal", MagicMock())

    state = MagicMock()
    message = MagicMock()
    message.answer = AsyncMock()
    message.successful_payment = SimpleNamespace(
        invoice_payload=bad_payload,
        telegram_payment_charge_id="tg",
    )

    await payment_module.successful_payment(message, state)

    message.answer.assert_awaited_once()
    args, _ = message.answer.call_args
    assert "ошибк" in args[0].lower() or "fail" in args[0].lower() or args[0] == payment_module.PAYMENT_FAILED


# ─── pre_checkout always approves ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pre_checkout_always_approves():
    """ТЗ §12.3: бот должен принимать pre-checkout, чтобы Telegram продолжил."""
    query = MagicMock()
    query.answer = AsyncMock()

    await payment_module.pre_checkout(query)

    query.answer.assert_awaited_once_with(ok=True)


# ─── cb_payment_cancel ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_payment_cancel_marks_payment_cancelled(monkeypatch):
    payment_repo = MagicMock()
    payment_repo.set_status = AsyncMock()

    @asynccontextmanager
    async def fake_session_local():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    monkeypatch.setattr(payment_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(payment_module, "PaymentRepository", lambda s: payment_repo)

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"payment_id": 99})
    state.clear = AsyncMock()

    call = MagicMock()
    call.message.edit_reply_markup = AsyncMock()
    call.message.answer = AsyncMock()
    call.answer = AsyncMock()

    await payment_module.cb_payment_cancel(call, state)

    payment_repo.set_status.assert_awaited_once_with(99, PaymentStatus.CANCELLED)
    state.clear.assert_awaited_once()
    call.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_payment_cancel_ok_when_no_payment_id(monkeypatch):
    """If state has no payment_id (rare race), we still close the FSM cleanly."""

    monkeypatch.setattr(payment_module, "AsyncSessionLocal", MagicMock())
    payment_repo = MagicMock()
    payment_repo.set_status = AsyncMock()
    monkeypatch.setattr(payment_module, "PaymentRepository", lambda s: payment_repo)

    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()

    call = MagicMock()
    call.message.edit_reply_markup = AsyncMock()
    call.message.answer = AsyncMock()
    call.answer = AsyncMock()

    await payment_module.cb_payment_cancel(call, state)

    payment_repo.set_status.assert_not_awaited()
    state.clear.assert_awaited_once()


# ─── cb_tariff_selected ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_tariff_selected_invalid_tariff():
    """Bogus tariff string must answer with an alert and not touch the DB."""
    state = MagicMock()
    call = MagicMock()
    call.data = "tariff:nonsense"
    call.answer = AsyncMock()
    call.message.edit_reply_markup = AsyncMock()

    bot = MagicMock()
    db_user = MagicMock()

    await payment_module.cb_tariff_selected(call, state, bot, db_user)

    call.answer.assert_awaited_with("Неверный тариф", show_alert=True)


@pytest.mark.asyncio
async def test_cb_tariff_selected_without_project_id_in_state():
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})

    call = MagicMock()
    call.data = "tariff:room"
    call.answer = AsyncMock()
    call.message.edit_reply_markup = AsyncMock()

    bot = MagicMock()
    db_user = MagicMock()

    await payment_module.cb_tariff_selected(call, state, bot, db_user)

    call.answer.assert_awaited_with("Ошибка: проект не найден", show_alert=True)


@pytest.mark.asyncio
async def test_cb_tariff_selected_free_tier_skips_invoice(monkeypatch):
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"project_id": 5})
    state.clear = AsyncMock()

    @asynccontextmanager
    async def fake_session_local():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    project_repo = MagicMock()
    project_repo.update_params = AsyncMock()

    user_repo = MagicMock()
    user_repo.increment_free_previews = AsyncMock()

    monkeypatch.setattr(payment_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(payment_module, "ProjectRepository", lambda s: project_repo)
    monkeypatch.setattr(payment_module, "UserRepository", lambda s: user_repo)

    enqueue = AsyncMock()
    monkeypatch.setattr(
        payment_module, "GenerationService",
        lambda s: SimpleNamespace(enqueue=enqueue),
    )

    call = MagicMock()
    call.data = "tariff:free"
    call.answer = AsyncMock()
    call.message.edit_reply_markup = AsyncMock()
    call.message.answer = AsyncMock()

    bot = MagicMock()
    bot.send_invoice = AsyncMock()
    db_user = SimpleNamespace(id=1)

    await payment_module.cb_tariff_selected(call, state, bot, db_user)

    project_repo.update_params.assert_awaited_once_with(5, tariff=Tariff.FREE.value)
    user_repo.increment_free_previews.assert_awaited_once_with(1)
    enqueue.assert_awaited_once_with(5)
    bot.send_invoice.assert_not_awaited()


@pytest.mark.asyncio
async def test_cb_tariff_selected_paid_tier_sends_invoice(monkeypatch):
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"project_id": 11})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    @asynccontextmanager
    async def fake_session_local():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    project_repo = MagicMock()
    project_repo.update_params = AsyncMock()

    payment = SimpleNamespace(id=77)
    payment_repo = MagicMock()
    payment_repo.create = AsyncMock(return_value=payment)

    monkeypatch.setattr(payment_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(payment_module, "ProjectRepository", lambda s: project_repo)
    monkeypatch.setattr(payment_module, "PaymentRepository", lambda s: payment_repo)

    call = MagicMock()
    call.data = "tariff:room"
    call.from_user.id = 4242
    call.answer = AsyncMock()
    call.message.edit_reply_markup = AsyncMock()

    bot = MagicMock()
    bot.send_invoice = AsyncMock()

    db_user = SimpleNamespace(id=1)

    with patch.object(payment_module.settings, "payment_token", "tg-pay-tok"):
        await payment_module.cb_tariff_selected(call, state, bot, db_user)

    project_repo.update_params.assert_awaited_once_with(11, tariff=Tariff.ROOM.value)
    payment_repo.create.assert_awaited_once()
    state.update_data.assert_awaited_once_with(payment_id=77)
    bot.send_invoice.assert_awaited_once()
    invoice_kwargs = bot.send_invoice.await_args.kwargs
    assert invoice_kwargs["chat_id"] == 4242
    assert invoice_kwargs["payload"] == "project:11:payment:77"
    assert invoice_kwargs["provider_token"] == "tg-pay-tok"
