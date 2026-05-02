"""Unit tests for LLM-driven concept and shopping list (ТЗ §13.6 / §13.7)."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.ai.llm_text import (
    LlmTextClient,
    ShoppingItem,
    ShoppingList,
    _project_fact_block,
)


# ─── Fact block ──────────────────────────────────────────────────────────────

def _make_project(**overrides):
    base = dict(
        room_type="kitchen",
        area_m2=18,
        ceiling_height=2.7,
        style="japandi",
        budget_tier="medium",
        free_space_percent=40,
        keep_items=None,
        extra_notes=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_analysis(**overrides):
    base = dict(
        scene_type="kitchen",
        main_objects=["sink", "fridge", "table"],
        has_windows=True,
        window_count=2,
        has_doors=True,
        door_count=1,
        floor_description="ламинат",
        walls_description="белая краска",
        ceiling_description="окрашенный белый",
        walking_zones="центр свободен",
        clutter_level="low",
        photo_quality="good",
        notes="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_fact_block_includes_present_fields():
    block = _project_fact_block(_make_project(), _make_analysis())
    for needle in [
        "Тип комнаты: kitchen",
        "Площадь, м²: 18",
        "Стиль: japandi",
        "Бюджет: medium",
        "Сцена: kitchen",
        "Окна: 2",
        "Двери: 1",
        "Захламлённость: low",
    ]:
        assert needle in block, f"missing {needle!r} in fact block"


def test_fact_block_omits_blank_or_none_fields():
    project = _make_project(
        keep_items=None,
        extra_notes="",
    )
    block = _project_fact_block(project, analysis=None)
    assert "Сохранить" not in block
    assert "Дополнительные пожелания" not in block
    assert "Сцена" not in block  # analysis was None


def test_fact_block_works_without_analysis():
    block = _project_fact_block(_make_project(), analysis=None)
    assert "Тип комнаты: kitchen" in block
    assert "Сцена" not in block


def test_fact_block_returns_placeholder_when_everything_blank():
    project = SimpleNamespace(
        room_type=None, area_m2=None, ceiling_height=None,
        style=None, budget_tier=None, free_space_percent=None,
        keep_items=None, extra_notes=None,
    )
    block = _project_fact_block(project, analysis=None)
    assert "(данных нет)" in block


# ─── Shopping list models ────────────────────────────────────────────────────

def test_shopping_item_defaults():
    item = ShoppingItem(category="Диван")
    assert item.description == ""
    assert item.color == ""
    assert item.price_range == ""


def test_shopping_list_to_dict_serialises_items():
    sl = ShoppingList(items=[
        ShoppingItem(category="Диван", price_range="30 000 ₽"),
        ShoppingItem(category="Стол"),
    ])
    out = sl.to_dict()
    assert out == {"items": [
        {"category": "Диван", "description": "", "color": "", "price_range": "30 000 ₽"},
        {"category": "Стол", "description": "", "color": "", "price_range": ""},
    ]}


# ─── is_configured guard ─────────────────────────────────────────────────────

@pytest.mark.parametrize("api_key,provider,expected", [
    ("", "openai", False),
    ("sk-x", "openai", True),
    ("sk-x", "", False),
    ("sk-x", "none", False),
    ("sk-x", "stub", False),
    ("sk-x", "anthropic", True),
])
def test_is_configured_handles_provider_and_key(api_key, provider, expected):
    client = LlmTextClient(api_key=api_key, provider=provider)
    assert client.is_configured is expected


# ─── build_concept ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_concept_returns_none_when_unconfigured():
    client = LlmTextClient(api_key="")
    result = await client.build_concept(_make_project(), _make_analysis())
    assert result is None


@pytest.mark.asyncio
async def test_build_concept_returns_text_on_happy_path():
    client = LlmTextClient(api_key="sk-test")
    payload = {
        "choices": [{
            "message": {
                "content": json.dumps({"text": "🎨 <b>Стиль:</b> Японди"}),
            }
        }],
    }
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status = MagicMock()

    async_client = MagicMock()
    async_client.post = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        result = await client.build_concept(_make_project(), _make_analysis())

    assert result == "🎨 <b>Стиль:</b> Японди"


@pytest.mark.asyncio
async def test_build_concept_strips_markdown_fences():
    client = LlmTextClient(api_key="sk-test")
    fenced = "```json\n" + json.dumps({"text": "ok"}) + "\n```"
    payload = {"choices": [{"message": {"content": fenced}}]}
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status = MagicMock()

    async_client = MagicMock()
    async_client.post = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        result = await client.build_concept(_make_project(), _make_analysis())

    assert result == "ok"


@pytest.mark.asyncio
async def test_build_concept_returns_none_on_http_error():
    client = LlmTextClient(api_key="sk-test")

    async_client = MagicMock()
    async_client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        result = await client.build_concept(_make_project(), _make_analysis())

    assert result is None


@pytest.mark.asyncio
async def test_build_concept_returns_none_on_invalid_json():
    client = LlmTextClient(api_key="sk-test")
    response = MagicMock()
    response.json.return_value = {
        "choices": [{"message": {"content": "this is not json"}}]
    }
    response.raise_for_status = MagicMock()

    async_client = MagicMock()
    async_client.post = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        result = await client.build_concept(_make_project(), _make_analysis())

    assert result is None


@pytest.mark.asyncio
async def test_build_concept_returns_none_when_text_missing():
    client = LlmTextClient(api_key="sk-test")
    response = MagicMock()
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"unrelated": "field"})}}]
    }
    response.raise_for_status = MagicMock()

    async_client = MagicMock()
    async_client.post = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        result = await client.build_concept(_make_project(), _make_analysis())

    assert result is None


# ─── build_shopping_list ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_shopping_list_returns_none_when_unconfigured():
    client = LlmTextClient(api_key="")
    result = await client.build_shopping_list(_make_project(), _make_analysis())
    assert result is None


@pytest.mark.asyncio
async def test_build_shopping_list_parses_valid_response():
    client = LlmTextClient(api_key="sk-test")
    items_payload = {
        "items": [
            {"category": "Диван", "description": "Низкий", "color": "Бежевый", "price_range": "30 000 – 80 000 ₽"},
            {"category": "Стол", "description": "Дерево", "color": "Дуб", "price_range": "15 000 ₽"},
        ]
    }
    response = MagicMock()
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(items_payload)}}]
    }
    response.raise_for_status = MagicMock()

    async_client = MagicMock()
    async_client.post = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        result = await client.build_shopping_list(_make_project(), _make_analysis())

    assert result is not None
    assert "items" in result
    assert len(result["items"]) == 2
    assert result["items"][0]["category"] == "Диван"
    assert result["items"][0]["price_range"] == "30 000 – 80 000 ₽"


@pytest.mark.asyncio
async def test_build_shopping_list_returns_none_for_empty_items():
    client = LlmTextClient(api_key="sk-test")
    response = MagicMock()
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"items": []})}}]
    }
    response.raise_for_status = MagicMock()

    async_client = MagicMock()
    async_client.post = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        result = await client.build_shopping_list(_make_project(), _make_analysis())

    assert result is None


@pytest.mark.asyncio
async def test_build_shopping_list_rejects_malformed_items():
    """Items missing the required 'category' field must invalidate the list."""
    client = LlmTextClient(api_key="sk-test")
    response = MagicMock()
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"items": [{"description": "No category"}]})}}]
    }
    response.raise_for_status = MagicMock()

    async_client = MagicMock()
    async_client.post = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        result = await client.build_shopping_list(_make_project(), _make_analysis())

    assert result is None


# ─── Payload shape ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_payload_uses_json_response_format_and_bearer_auth():
    client = LlmTextClient(api_key="sk-foo", model="gpt-4o-mini")

    captured: dict = {}

    async def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"text": "hi"})}}]
        }
        response.raise_for_status = MagicMock()
        return response

    async_client = MagicMock()
    async_client.post = AsyncMock(side_effect=fake_post)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        await client.build_concept(_make_project(), _make_analysis())

    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-foo"
    payload = captured["json"]
    assert payload["model"] == "gpt-4o-mini"
    assert payload["response_format"] == {"type": "json_object"}
    # System + user messages, system contains formatting rules, user contains facts.
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert "Тип комнаты: kitchen" in payload["messages"][1]["content"]


@pytest.mark.asyncio
async def test_shopping_payload_routes_to_shopping_system_prompt():
    client = LlmTextClient(api_key="sk-foo")

    captured: dict = {}

    async def fake_post(url, **kwargs):
        captured["json"] = kwargs.get("json")
        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"items": [
                {"category": "Диван", "price_range": "30 000 ₽"},
            ]})}}]
        }
        response.raise_for_status = MagicMock()
        return response

    async_client = MagicMock()
    async_client.post = AsyncMock(side_effect=fake_post)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.ai.llm_text.httpx.AsyncClient", return_value=async_client):
        await client.build_shopping_list(_make_project(), _make_analysis())

    system_prompt = captured["json"]["messages"][0]["content"]
    assert "shopping" in system_prompt.lower() or "items" in system_prompt
    assert "JSON" in system_prompt
