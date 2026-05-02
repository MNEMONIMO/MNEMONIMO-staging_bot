"""Vision-analysis client for the AI pipeline (ТЗ §13.2).

The bot must extract structured info about a room photo (scene type, main
objects, windows/doors, surfaces, walking zones, clutter, photo quality)
before generating images. This module wraps an OpenAI-compatible
``/chat/completions`` endpoint with a JSON response schema.

Design goals:

* Pure ``httpx``: no SDK, no extra dependency.
* Provider-agnostic: any service that speaks the OpenAI Chat Completions
  protocol (OpenAI, Together, Groq, OpenRouter, vLLM proxies) works by
  pointing ``vision_base_url`` / ``vision_model`` at it.
* Defensive: every failure path returns a usable stub instead of raising
  so the rest of the generation pipeline keeps running.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Literal, Optional

import httpx
from loguru import logger
from pydantic import BaseModel, Field, ValidationError


CLUTTER_LEVELS = ("low", "medium", "high")
PHOTO_QUALITIES = ("poor", "ok", "good")


class PhotoAnalysis(BaseModel):
    """Structured room analysis. Fields mirror ТЗ §13.2."""

    scene_type: str = Field(default="unknown", description="Detected room type label.")
    main_objects: list[str] = Field(default_factory=list)
    has_windows: bool = False
    window_count: int = 0
    has_doors: bool = False
    door_count: int = 0
    floor_description: str = ""
    walls_description: str = ""
    ceiling_description: str = ""
    walking_zones: str = ""
    clutter_level: Literal["low", "medium", "high"] = "medium"
    photo_quality: Literal["poor", "ok", "good"] = "ok"
    notes: str = ""

    @classmethod
    def stub(cls) -> "PhotoAnalysis":
        """Default analysis used when no vision provider is configured."""
        return cls(scene_type="unknown", clutter_level="medium", photo_quality="ok")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


_SYSTEM_PROMPT = (
    "You are an interior-photo analyst. Examine the supplied photo of a room "
    "and return ONLY a JSON object with the keys defined below. Do not include "
    "prose, explanations, or markdown — just JSON.\n\n"
    "Required keys (and their types):\n"
    '  scene_type (string; one of: "kitchen", "bedroom", "living", "kids", '
    '    "bathroom", "office", "hallway", "other", "unknown"),\n'
    "  main_objects (array of short strings — sofa, table, fridge, …),\n"
    "  has_windows (boolean),\n"
    "  window_count (integer),\n"
    "  has_doors (boolean),\n"
    "  door_count (integer),\n"
    "  floor_description (string — material + colour, e.g. \"oak parquet, light\"),\n"
    "  walls_description (string),\n"
    "  ceiling_description (string),\n"
    "  walking_zones (short string describing free passage areas),\n"
    "  clutter_level (one of: \"low\", \"medium\", \"high\"),\n"
    "  photo_quality (one of: \"poor\", \"ok\", \"good\"),\n"
    "  notes (short string with anything else worth flagging — defects, "
    "    unusual angle, severe lighting issues; empty string if none).\n"
)

_USER_PROMPT = (
    "Analyse the attached room photo and respond with the JSON object."
)


class VisionClient:
    """Calls an OpenAI-compatible chat completions endpoint for photo analysis."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 30,
        provider: str = "openai",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._provider = provider

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key) and self._provider not in ("", "none", "stub")

    async def analyze(self, image_bytes: bytes) -> PhotoAnalysis:
        """Run the full vision pipeline. Always returns a ``PhotoAnalysis``.

        Falls back to ``PhotoAnalysis.stub()`` if the provider is disabled,
        the network call fails, or the response is unparseable. The caller
        therefore never has to guard against ``None``.
        """
        if not self.is_configured:
            logger.debug("Vision provider not configured; returning stub analysis.")
            return PhotoAnalysis.stub()

        try:
            payload = self._build_payload(image_bytes)
        except ValueError as exc:
            logger.warning(f"Vision payload could not be built: {exc}")
            return PhotoAnalysis.stub()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            logger.warning(f"Vision API call failed: {exc!r}")
            return PhotoAnalysis.stub()

        return self._parse_response(body) or PhotoAnalysis.stub()

    # ── Internals ────────────────────────────────────────────────────────────

    def _build_payload(self, image_bytes: bytes) -> dict[str, Any]:
        if not image_bytes:
            raise ValueError("image_bytes is empty")
        b64 = base64.b64encode(image_bytes).decode()
        return {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "max_tokens": 800,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "low",
                            },
                        },
                    ],
                },
            ],
        }

    @staticmethod
    def _parse_response(body: dict[str, Any]) -> Optional[PhotoAnalysis]:
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning(f"Vision response had unexpected shape: {exc!r}")
            return None

        # OpenAI sometimes returns the JSON wrapped in markdown fences.
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(f"Vision response was not valid JSON: {exc!r}")
            return None

        try:
            return PhotoAnalysis.model_validate(data)
        except ValidationError as exc:
            logger.warning(f"Vision response failed validation: {exc!r}")
            return None
