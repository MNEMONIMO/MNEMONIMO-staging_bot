"""LLM-driven concept text and shopping list (ТЗ §13.6 / §13.7).

Wraps an OpenAI-compatible ``/chat/completions`` endpoint to turn a
:class:`~app.integrations.ai.vision.PhotoAnalysis` plus a
:class:`~app.db.models.Project` into:

* a short Russian-language concept blurb (``LlmTextClient.build_concept``),
* an approximate shopping list (``LlmTextClient.build_shopping_list``).

If the provider is not configured or the call fails, both methods return
``None`` so callers can fall back to the static templates that already
exist in :mod:`app.services.generation.service`.

Reuses the same API key / base URL as the vision client, since OpenAI
keys cover both text and multimodal endpoints.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx
from loguru import logger
from pydantic import BaseModel, Field, ValidationError


class ShoppingItem(BaseModel):
    """One row of the shopping list (ТЗ §13.7)."""

    category: str
    description: str = ""
    color: str = ""
    price_range: str = ""


class ShoppingList(BaseModel):
    items: list[ShoppingItem] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.model_dump() for item in self.items]}


_CONCEPT_SYSTEM_PROMPT = (
    "Ты — лид-дизайнер интерьеров. На основе фактов о комнате и параметров "
    "проекта составь короткий концепт-текст по-русски (4–6 строк, формат "
    "Telegram HTML). Каждая строка — одна из тем:\n"
    "  🎨 <b>Стиль:</b> ...\n"
    "  💡 <b>Идея:</b> ...\n"
    "  🚶 <b>Свободное пространство:</b> ...\n"
    "  ✨ <b>Акценты:</b> ...\n"
    "  💰 <b>Бюджет:</b> ...\n"
    "  📝 <b>Учтено:</b> ... (опционально, если есть extra_notes)\n"
    "Используй только теги <b>...</b>; запрещены <p>, <br>, ```, эмодзи "
    "других видов, маркдаун. Верни JSON-объект {\"text\": \"...\"} без "
    "лишних обёрток."
)

_SHOPPING_SYSTEM_PROMPT = (
    "Ты — байер интерьерного магазина. Составь приблизительный shopping-list "
    "в JSON. Формат:\n"
    "{\n"
    '  "items": [\n'
    '    {"category": "...", "description": "...", "color": "...", '
    '     "price_range": "5 000 – 20 000 ₽"},\n'
    "    ...\n"
    "  ]\n"
    "}\n"
    "Требования: 4–6 пунктов, описания короткие (≤80 символов), цены — "
    "правдоподобные диапазоны в рублях с разделителем тысяч пробелом и "
    "знаком ₽. Никакого текста вне JSON."
)


def _project_fact_block(project: Any, analysis: Any) -> str:
    """Render project + analysis into a compact bullet list for the LLM."""
    facts: list[str] = []

    def add(label: str, value: Any) -> None:
        if value is None or value == "" or value == []:
            return
        facts.append(f"- {label}: {value}")

    add("Тип комнаты", getattr(project, "room_type", None))
    add("Площадь, м²", getattr(project, "area_m2", None))
    add("Высота потолка, м", getattr(project, "ceiling_height", None))
    add("Стиль", getattr(project, "style", None))
    add("Бюджет", getattr(project, "budget_tier", None))
    add("Свободное пространство", getattr(project, "free_space_percent", None))
    add("Сохранить", getattr(project, "keep_items", None))
    add("Дополнительные пожелания", getattr(project, "extra_notes", None))

    if analysis is not None:
        add("Сцена", getattr(analysis, "scene_type", None))
        objects = getattr(analysis, "main_objects", None) or []
        if objects:
            add("Объекты", ", ".join(objects[:8]))
        if getattr(analysis, "has_windows", False):
            add("Окна", getattr(analysis, "window_count", 0) or "есть")
        if getattr(analysis, "has_doors", False):
            add("Двери", getattr(analysis, "door_count", 0) or "есть")
        add("Пол", getattr(analysis, "floor_description", None))
        add("Стены", getattr(analysis, "walls_description", None))
        add("Потолок", getattr(analysis, "ceiling_description", None))
        add("Зоны прохода", getattr(analysis, "walking_zones", None))
        add("Захламлённость", getattr(analysis, "clutter_level", None))
        add("Качество фото", getattr(analysis, "photo_quality", None))

    return "\n".join(facts) if facts else "(данных нет)"


class LlmTextClient:
    """Concept-blurb and shopping-list generator backed by an LLM."""

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

    # ── Public API ───────────────────────────────────────────────────────────

    async def build_concept(self, project: Any, analysis: Any = None) -> Optional[str]:
        """Return an HTML-formatted concept blurb, or ``None`` on failure."""
        if not self.is_configured:
            return None
        body = await self._chat(
            system=_CONCEPT_SYSTEM_PROMPT,
            user=f"Параметры проекта:\n{_project_fact_block(project, analysis)}",
            max_tokens=400,
        )
        if body is None:
            return None
        text = self._extract_field(body, "text")
        if not text or not text.strip():
            return None
        return text.strip()

    async def build_shopping_list(
        self, project: Any, analysis: Any = None,
    ) -> Optional[dict[str, Any]]:
        """Return ``{"items": [...]}``, or ``None`` if the LLM was unhappy."""
        if not self.is_configured:
            return None
        body = await self._chat(
            system=_SHOPPING_SYSTEM_PROMPT,
            user=f"Проект:\n{_project_fact_block(project, analysis)}",
            max_tokens=600,
        )
        if body is None:
            return None
        return self._extract_shopping_list(body)

    # ── Internals ────────────────────────────────────────────────────────────

    async def _chat(
        self, system: str, user: str, max_tokens: int = 600,
    ) -> Optional[dict[str, Any]]:
        payload = {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
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
                return response.json()
        except httpx.HTTPError as exc:
            logger.warning(f"LLM call failed: {exc!r}")
            return None

    @staticmethod
    def _extract_content(body: dict[str, Any]) -> Optional[str]:
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning(f"LLM response had unexpected shape: {exc!r}")
            return None
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        return text

    @classmethod
    def _extract_field(cls, body: dict[str, Any], field: str) -> Optional[str]:
        text = cls._extract_content(body)
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(f"LLM response was not valid JSON: {exc!r}")
            return None
        value = data.get(field)
        if not isinstance(value, str):
            return None
        return value

    @classmethod
    def _extract_shopping_list(
        cls, body: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        text = cls._extract_content(body)
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(f"LLM response was not valid JSON: {exc!r}")
            return None
        try:
            sl = ShoppingList.model_validate(data)
        except ValidationError as exc:
            logger.warning(f"LLM shopping-list failed validation: {exc!r}")
            return None
        if not sl.items:
            return None
        return sl.to_dict()
