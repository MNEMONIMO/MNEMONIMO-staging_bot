"""Tests for the vision-analysis client (ТЗ §13.2)."""
from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest


# ─── PhotoAnalysis schema ─────────────────────────────────────────────────────

def test_photo_analysis_stub_has_safe_defaults():
    from app.integrations.ai.vision import PhotoAnalysis

    stub = PhotoAnalysis.stub()

    assert stub.scene_type == "unknown"
    assert stub.clutter_level == "medium"
    assert stub.photo_quality == "ok"
    assert stub.main_objects == []
    assert stub.window_count == 0
    assert stub.has_windows is False


def test_photo_analysis_to_dict_roundtrip():
    from app.integrations.ai.vision import PhotoAnalysis

    a = PhotoAnalysis(
        scene_type="kitchen",
        main_objects=["fridge", "stove"],
        has_windows=True,
        window_count=2,
        clutter_level="low",
        photo_quality="good",
    )
    d = a.to_dict()
    assert d["scene_type"] == "kitchen"
    assert d["main_objects"] == ["fridge", "stove"]
    assert d["window_count"] == 2

    restored = PhotoAnalysis.model_validate(d)
    assert restored == a


def test_photo_analysis_validates_enum_fields():
    from app.integrations.ai.vision import PhotoAnalysis
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PhotoAnalysis(clutter_level="extreme")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        PhotoAnalysis(photo_quality="terrible")  # type: ignore[arg-type]


# ─── VisionClient configuration ───────────────────────────────────────────────

def test_vision_client_unconfigured_when_api_key_empty():
    from app.integrations.ai.vision import VisionClient

    client = VisionClient(api_key="", model="gpt-4o-mini")
    assert client.is_configured is False


def test_vision_client_unconfigured_when_provider_disabled():
    from app.integrations.ai.vision import VisionClient

    client = VisionClient(api_key="key", provider="none")
    assert client.is_configured is False


def test_vision_client_configured_with_key_and_provider():
    from app.integrations.ai.vision import VisionClient

    client = VisionClient(api_key="sk-test", provider="openai")
    assert client.is_configured is True


# ─── analyze() return paths ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_returns_stub_when_unconfigured():
    from app.integrations.ai.vision import VisionClient, PhotoAnalysis

    client = VisionClient(api_key="")
    result = await client.analyze(b"\xff\xd8\xff fake jpeg")

    assert result == PhotoAnalysis.stub()


@pytest.mark.asyncio
async def test_analyze_returns_stub_for_empty_image_bytes():
    from app.integrations.ai.vision import VisionClient, PhotoAnalysis

    client = VisionClient(api_key="sk-test")
    result = await client.analyze(b"")

    assert result == PhotoAnalysis.stub()


@pytest.mark.asyncio
async def test_analyze_parses_valid_openai_response():
    from app.integrations.ai.vision import VisionClient

    payload = {
        "scene_type": "kitchen",
        "main_objects": ["fridge", "stove", "table"],
        "has_windows": True,
        "window_count": 1,
        "has_doors": True,
        "door_count": 1,
        "floor_description": "tile, light grey",
        "walls_description": "white paint",
        "ceiling_description": "white, flat",
        "walking_zones": "L-shaped corridor along the right wall",
        "clutter_level": "low",
        "photo_quality": "good",
        "notes": "",
    }
    fake_response = {"choices": [{"message": {"content": json.dumps(payload)}}]}

    client = VisionClient(api_key="sk-test")
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(
        return_value=httpx.Response(200, json=fake_response, request=httpx.Request("POST", "x")),
    )):
        result = await client.analyze(b"\xff\xd8\xff fake jpeg")

    assert result.scene_type == "kitchen"
    assert result.main_objects == ["fridge", "stove", "table"]
    assert result.has_windows is True
    assert result.window_count == 1
    assert result.photo_quality == "good"


@pytest.mark.asyncio
async def test_analyze_strips_markdown_fences_around_json():
    from app.integrations.ai.vision import VisionClient

    payload = {
        "scene_type": "bedroom",
        "main_objects": ["bed"],
        "has_windows": False,
        "window_count": 0,
        "has_doors": True,
        "door_count": 1,
        "floor_description": "wood",
        "walls_description": "beige",
        "ceiling_description": "white",
        "walking_zones": "centre",
        "clutter_level": "medium",
        "photo_quality": "ok",
        "notes": "",
    }
    wrapped = "```json\n" + json.dumps(payload) + "\n```"
    fake_response = {"choices": [{"message": {"content": wrapped}}]}

    client = VisionClient(api_key="sk-test")
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(
        return_value=httpx.Response(200, json=fake_response, request=httpx.Request("POST", "x")),
    )):
        result = await client.analyze(b"\xff\xd8\xff fake jpeg")

    assert result.scene_type == "bedroom"


@pytest.mark.asyncio
async def test_analyze_falls_back_to_stub_on_http_error():
    from app.integrations.ai.vision import VisionClient, PhotoAnalysis

    client = VisionClient(api_key="sk-test")
    with patch.object(
        httpx.AsyncClient,
        "post",
        new=AsyncMock(side_effect=httpx.ConnectError("boom")),
    ):
        result = await client.analyze(b"\xff\xd8\xff fake jpeg")

    assert result == PhotoAnalysis.stub()


@pytest.mark.asyncio
async def test_analyze_falls_back_to_stub_on_invalid_json():
    from app.integrations.ai.vision import VisionClient, PhotoAnalysis

    fake_response = {"choices": [{"message": {"content": "not-json {{{"}}]}
    client = VisionClient(api_key="sk-test")
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(
        return_value=httpx.Response(200, json=fake_response, request=httpx.Request("POST", "x")),
    )):
        result = await client.analyze(b"\xff\xd8\xff fake jpeg")

    assert result == PhotoAnalysis.stub()


@pytest.mark.asyncio
async def test_analyze_falls_back_when_response_missing_choices():
    from app.integrations.ai.vision import VisionClient, PhotoAnalysis

    fake_response = {"foo": "bar"}
    client = VisionClient(api_key="sk-test")
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(
        return_value=httpx.Response(200, json=fake_response, request=httpx.Request("POST", "x")),
    )):
        result = await client.analyze(b"\xff\xd8\xff fake jpeg")

    assert result == PhotoAnalysis.stub()


# ─── Payload construction ─────────────────────────────────────────────────────

def test_vision_payload_includes_base64_image_and_json_response_format():
    from app.integrations.ai.vision import VisionClient

    client = VisionClient(api_key="sk-test", model="custom-model")
    payload = client._build_payload(b"hello-bytes")

    assert payload["model"] == "custom-model"
    assert payload["response_format"] == {"type": "json_object"}
    user_msg = payload["messages"][1]
    assert user_msg["role"] == "user"
    image_part = next(p for p in user_msg["content"] if p["type"] == "image_url")
    expected_b64 = base64.b64encode(b"hello-bytes").decode()
    assert expected_b64 in image_part["image_url"]["url"]


# ─── build_image_prompt integrates analysis ────────────────────────────────────

def test_prompt_builder_includes_analysis_hints():
    from app.integrations.ai.client import build_image_prompt
    from app.integrations.ai.vision import PhotoAnalysis

    project = type("P", (), {
        "room_type": "kitchen",
        "style": "japandi",
        "budget_tier": "medium",
        "area_m2": 12,
        "ceiling_height": 2.7,
        "free_space_percent": "40",
        "keep_items": None,
        "extra_notes": None,
    })()

    analysis = PhotoAnalysis(
        scene_type="kitchen",
        main_objects=["fridge", "stove", "table"],
        has_windows=True,
        window_count=2,
        has_doors=True,
        door_count=1,
        floor_description="tile, light grey",
        walls_description="white paint",
        ceiling_description="white, flat",
        walking_zones="L-shape along the right wall",
        clutter_level="low",
        photo_quality="good",
    )

    prompt = build_image_prompt(project, analysis=analysis)

    assert "preserve existing 2 windows" in prompt
    assert "keep 1 door" in prompt
    assert "floor: tile, light grey" in prompt
    assert "walking zones: L-shape along the right wall" in prompt
    assert "fridge" in prompt


def test_prompt_builder_works_without_analysis():
    from app.integrations.ai.client import build_image_prompt

    project = type("P", (), {
        "room_type": "bedroom",
        "style": "modern",
        "budget_tier": None,
        "area_m2": None,
        "ceiling_height": None,
        "free_space_percent": None,
        "keep_items": None,
        "extra_notes": None,
    })()

    prompt = build_image_prompt(project)
    assert "bedroom interior" in prompt
    assert "modern interior design" in prompt
