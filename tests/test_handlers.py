"""Smoke + behavioural tests for the bot handler layer.

These tests don't talk to Telegram or to a real database — they exercise the
pure-Python helpers that recently regressed (result keyboard wiring, the
/cancel command, the result-button callback parser) so that future refactors
notice if any of these break again.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─── result_keyboard ──────────────────────────────────────────────────────────

def test_result_keyboard_encodes_project_id():
    from app.bot.keyboards.keyboards import result_keyboard

    markup = result_keyboard(project_id=42, has_free_plan=True)
    flat = [b for row in markup.inline_keyboard for b in row]
    cbs = [b.callback_data for b in flat]

    assert "result:retry:42" in cbs
    assert "result:change_style:42" in cbs
    assert "result:new_project" in cbs
    assert "result:upgrade" in cbs
    assert "result:my_projects" in cbs


def test_result_keyboard_without_project_id_omits_suffix():
    from app.bot.keyboards.keyboards import result_keyboard

    markup = result_keyboard()
    cbs = [b.callback_data for row in markup.inline_keyboard for b in row]

    assert "result:retry" in cbs
    assert "result:change_style" in cbs
    # No "Купить" button when has_free_plan is False
    assert "result:upgrade" not in cbs


def test_result_keyboard_hides_upgrade_for_paid_users():
    from app.bot.keyboards.keyboards import result_keyboard

    markup = result_keyboard(project_id=1, has_free_plan=False)
    cbs = [b.callback_data for row in markup.inline_keyboard for b in row]

    assert "result:upgrade" not in cbs


# ─── result callback parser ───────────────────────────────────────────────────

@pytest.mark.parametrize("data,expected", [
    ("result:retry:7", 7),
    ("result:change_style:123", 123),
    ("result:retry", None),
    ("result:change_style", None),
    ("result:retry:notanumber", None),
])
def test_parse_result_project_id(data, expected):
    from app.bot.handlers.my_projects import _parse_result_project_id

    call = MagicMock()
    call.data = data
    assert _parse_result_project_id(call) == expected


# ─── /cancel handler ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_clears_active_state():
    from app.bot.handlers.start import cmd_cancel

    state = MagicMock()
    state.get_state = AsyncMock(return_value="ProjectForm:area")
    state.clear = AsyncMock()
    message = MagicMock()
    message.answer = AsyncMock()

    await cmd_cancel(message, state)

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    args, _ = message.answer.call_args
    assert "отмен" in args[0].lower()


@pytest.mark.asyncio
async def test_cancel_no_active_state():
    from app.bot.handlers.start import cmd_cancel

    state = MagicMock()
    state.get_state = AsyncMock(return_value=None)
    state.clear = AsyncMock()
    message = MagicMock()
    message.answer = AsyncMock()

    await cmd_cancel(message, state)

    state.clear.assert_awaited_once()
    args, _ = message.answer.call_args
    assert "нет активного" in args[0].lower()


# ─── Module imports (smoke) ───────────────────────────────────────────────────

def test_all_bot_handlers_import():
    from app.bot.handlers import start, project, payment, my_projects, admin  # noqa: F401
    from app.bot.middlewares import auth, rate_limit  # noqa: F401
    from app.bot.main import create_bot, create_dispatcher  # noqa: F401


def test_alembic_initial_migration_present():
    from pathlib import Path

    versions_dir = Path("app/db/migrations/versions")
    py_files = sorted(p for p in versions_dir.glob("*.py") if not p.name.startswith("_"))
    assert py_files, "no alembic revision files found in app/db/migrations/versions"
    # The initial migration must exist and define down_revision = None
    text = py_files[0].read_text()
    assert "down_revision = None" in text
    assert "def upgrade" in text and "def downgrade" in text
