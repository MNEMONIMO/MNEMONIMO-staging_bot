"""Unit tests for the admin handlers (ТЗ §17 admin panel)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import admin as admin_module
from app.db.models import ProjectStatus


# ─── is_admin guard ───────────────────────────────────────────────────────────

def test_is_admin_returns_true_for_listed_id(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [42, 100])
    assert admin_module.is_admin(42) is True
    assert admin_module.is_admin(100) is True


def test_is_admin_returns_false_for_unlisted_id(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [42])
    assert admin_module.is_admin(7) is False
    assert admin_module.is_admin(0) is False


def test_is_admin_returns_false_for_empty_admin_list(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [])
    assert admin_module.is_admin(42) is False


# ─── @admin_only decorator ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_only_blocks_non_admin(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    inner = AsyncMock(return_value="should-not-run")
    wrapped = admin_module.admin_only(inner)

    event = MagicMock()
    event.from_user.id = 999
    event.answer = AsyncMock()

    result = await wrapped(event)

    inner.assert_not_awaited()
    event.answer.assert_awaited_once()
    args, _ = event.answer.call_args
    assert "доступ" in args[0].lower() or "🚫" in args[0]
    assert result is None


@pytest.mark.asyncio
async def test_admin_only_allows_admin(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    inner = AsyncMock(return_value="ok")
    wrapped = admin_module.admin_only(inner)

    event = MagicMock()
    event.from_user.id = 1
    event.answer = AsyncMock()

    result = await wrapped(event)

    inner.assert_awaited_once_with(event)
    assert result == "ok"


@pytest.mark.asyncio
async def test_admin_only_safe_when_event_lacks_from_user(monkeypatch):
    """Defensive: edge cases like service updates must not crash the bot."""
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    inner = AsyncMock()
    wrapped = admin_module.admin_only(inner)

    # Stripped-down event without from_user attribute.
    event = SimpleNamespace()

    result = await wrapped(event)

    inner.assert_not_awaited()
    assert result is None


# ─── /admin command ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_admin_lists_subcommands_for_admin(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [42])

    message = MagicMock()
    message.from_user.id = 42
    message.answer = AsyncMock()

    await admin_module.cmd_admin(message)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    for cmd in ("/projects", "/stats", "/broadcast", "/project", "/retry"):
        assert cmd in text


# ─── /retry <id> ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_retry_rejects_missing_id(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    message = MagicMock()
    message.from_user.id = 1
    message.text = "/retry"
    message.answer = AsyncMock()

    await admin_module.cmd_retry(message)
    message.answer.assert_awaited_once()
    assert "/retry" in message.answer.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_cmd_retry_rejects_non_numeric_id(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    message = MagicMock()
    message.from_user.id = 1
    message.text = "/retry foo"
    message.answer = AsyncMock()

    await admin_module.cmd_retry(message)
    message.answer.assert_awaited_once()
    assert "числом" in message.answer.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_cmd_retry_enqueues_when_args_valid(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    enqueue = AsyncMock()

    @asynccontextmanager
    async def fake_session_local():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    monkeypatch.setattr(admin_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(
        admin_module,
        "GenerationService",
        lambda s: SimpleNamespace(enqueue=enqueue),
    )

    message = MagicMock()
    message.from_user.id = 1
    message.text = "/retry 17"
    message.answer = AsyncMock()

    await admin_module.cmd_retry(message)

    enqueue.assert_awaited_once_with(17)
    message.answer.assert_awaited()
    assert "✅" in message.answer.await_args.args[0]


# ─── /project <id> ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_project_detail_rejects_missing_arg(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    message = MagicMock()
    message.from_user.id = 1
    message.text = "/project"
    message.answer = AsyncMock()

    await admin_module.cmd_project_detail(message)
    args = message.answer.await_args.args[0].lower()
    assert "/project" in args


@pytest.mark.asyncio
async def test_cmd_project_detail_handles_missing_project(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    @asynccontextmanager
    async def fake_session_local():
        yield MagicMock()

    project_repo = MagicMock()
    project_repo.get_by_id = AsyncMock(return_value=None)

    monkeypatch.setattr(admin_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(admin_module, "ProjectRepository", lambda s: project_repo)

    message = MagicMock()
    message.from_user.id = 1
    message.text = "/project 999"
    message.answer = AsyncMock()

    await admin_module.cmd_project_detail(message)
    project_repo.get_by_id.assert_awaited_once_with(999)
    assert "не найден" in message.answer.await_args.args[0]


# ─── inline admin buttons ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_admin_done_marks_project_done(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    project_repo = MagicMock()
    project_repo.set_status = AsyncMock()

    @asynccontextmanager
    async def fake_session_local():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    monkeypatch.setattr(admin_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(admin_module, "ProjectRepository", lambda s: project_repo)

    call = MagicMock()
    call.from_user.id = 1
    call.data = "admin_done:55"
    call.answer = AsyncMock()
    call.message.edit_reply_markup = AsyncMock()

    await admin_module.cb_admin_done(call)
    project_repo.set_status.assert_awaited_once_with(55, ProjectStatus.DONE)
    call.answer.assert_awaited()


@pytest.mark.asyncio
async def test_cb_admin_cancel_marks_project_cancelled(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    project_repo = MagicMock()
    project_repo.set_status = AsyncMock()

    @asynccontextmanager
    async def fake_session_local():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    monkeypatch.setattr(admin_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(admin_module, "ProjectRepository", lambda s: project_repo)

    call = MagicMock()
    call.from_user.id = 1
    call.data = "admin_cancel:8"
    call.answer = AsyncMock()
    call.message.edit_reply_markup = AsyncMock()

    await admin_module.cb_admin_cancel(call)
    project_repo.set_status.assert_awaited_once_with(8, ProjectStatus.CANCELLED)


@pytest.mark.asyncio
async def test_cb_admin_retry_calls_generation_service(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    enqueue = AsyncMock()

    @asynccontextmanager
    async def fake_session_local():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    monkeypatch.setattr(admin_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(
        admin_module,
        "GenerationService",
        lambda s: SimpleNamespace(enqueue=enqueue),
    )

    call = MagicMock()
    call.from_user.id = 1
    call.data = "admin_retry:12"
    call.answer = AsyncMock()

    await admin_module.cb_admin_retry(call)
    enqueue.assert_awaited_once_with(12)
    call.answer.assert_awaited()


# ─── /broadcast ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_start_sets_fsm_state(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    state = MagicMock()
    state.set_state = AsyncMock()

    message = MagicMock()
    message.from_user.id = 1
    message.answer = AsyncMock()

    await admin_module.cmd_broadcast_start(message, state)

    state.set_state.assert_awaited_once_with(admin_module.AdminFlow.waiting_broadcast_text)
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_send_rejects_empty_text(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    state = MagicMock()
    state.clear = AsyncMock()

    message = MagicMock()
    message.from_user.id = 1
    message.text = None
    message.caption = None
    message.answer = AsyncMock()

    await admin_module.cmd_broadcast_send(message, state)

    state.clear.assert_not_called()
    message.answer.assert_awaited_once()
    assert "пустым" in message.answer.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_broadcast_send_dispatches_to_active_users(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    @asynccontextmanager
    async def fake_session_local():
        yield MagicMock()

    user_repo = MagicMock()
    user_repo.list_all = AsyncMock(return_value=[
        SimpleNamespace(telegram_id=10, is_blocked=False),
        SimpleNamespace(telegram_id=20, is_blocked=True),  # filtered out
        SimpleNamespace(telegram_id=30, is_blocked=False),
    ])

    monkeypatch.setattr(admin_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(admin_module, "UserRepository", lambda s: user_repo)

    notifier = MagicMock()
    notifier.broadcast = AsyncMock(return_value={"sent": 2, "failed": 0})
    monkeypatch.setattr(admin_module, "NotificationService", lambda: notifier)

    state = MagicMock()
    state.clear = AsyncMock()

    message = MagicMock()
    message.from_user.id = 1
    message.text = "Hello everyone"
    message.caption = None
    message.answer = AsyncMock()

    await admin_module.cmd_broadcast_send(message, state)

    notifier.broadcast.assert_awaited_once()
    text_arg, ids_arg = notifier.broadcast.await_args.args
    assert text_arg == "Hello everyone"
    assert ids_arg == [10, 30]  # blocked user excluded


# ─── /stats ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_stats_aggregates_users_and_projects(monkeypatch):
    monkeypatch.setattr(admin_module.settings, "admin_ids", [1])

    @asynccontextmanager
    async def fake_session_local():
        yield MagicMock()

    project_repo = MagicMock()
    project_repo.count_by_status = AsyncMock(return_value={
        ProjectStatus.DONE: 5,
        ProjectStatus.FAILED: 1,
        ProjectStatus.QUEUED: 2,
    })

    user_repo = MagicMock()
    user_repo.list_all = AsyncMock(return_value=[
        SimpleNamespace(is_blocked=False),
        SimpleNamespace(is_blocked=False),
        SimpleNamespace(is_blocked=True),
    ])

    monkeypatch.setattr(admin_module, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(admin_module, "ProjectRepository", lambda s: project_repo)
    monkeypatch.setattr(admin_module, "UserRepository", lambda s: user_repo)

    message = MagicMock()
    message.from_user.id = 1
    message.answer = AsyncMock()

    await admin_module.cmd_stats(message)

    text = message.answer.await_args.args[0]
    assert "Пользователей: 3" in text
    assert "заблокировано: 1" in text
    assert "Проектов всего: 8" in text
    assert "Завершено: 5" in text
    assert "Ошибок: 1" in text
