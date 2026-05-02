import pytest


# ─── Area validation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("18", 18.0),
    ("24.5", 24.5),
    ("3", 3.0),
    ("200", 200.0),
])
def test_area_valid(value, expected):
    text = value.replace(",", ".")
    area = float(text)
    assert 3 <= area <= 200
    assert area == expected


@pytest.mark.parametrize("value", ["0", "201", "abc", "", "-5", "2.9"])
def test_area_invalid(value):
    try:
        text = value.replace(",", ".")
        area = float(text)
        valid = 3 <= area <= 200
    except ValueError:
        valid = False
    assert not valid


# ─── Ceiling height validation ────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("2.7", 2.7),
    ("3.0", 3.0),
    ("1.8", 1.8),
    ("6.0", 6.0),
])
def test_ceiling_valid(value, expected):
    height = float(value.replace(",", "."))
    assert 1.8 <= height <= 6.0
    assert abs(height - expected) < 0.001


@pytest.mark.parametrize("value", ["1.7", "6.1", "0", "abc"])
def test_ceiling_invalid(value):
    try:
        height = float(value.replace(",", "."))
        valid = 1.8 <= height <= 6.0
    except ValueError:
        valid = False
    assert not valid


# ─── Tariff prices ────────────────────────────────────────────────────────────

def test_tariff_prices():
    from app.services.payments.service import TARIFF_PRICES
    from app.db.models import Tariff

    assert TARIFF_PRICES[Tariff.FREE] == 0
    assert TARIFF_PRICES[Tariff.ROOM] == 49900
    assert TARIFF_PRICES[Tariff.PRO_ROOM] == 99900
    assert TARIFF_PRICES[Tariff.FLAT] == 199900
    assert TARIFF_PRICES[Tariff.REALTOR_PACK] == 299900


# ─── Variant count per tariff ─────────────────────────────────────────────────

def test_variant_count():
    from app.services.generation.service import TARIFF_VARIANTS
    from app.db.models import Tariff

    assert TARIFF_VARIANTS[Tariff.FREE] == 1
    assert TARIFF_VARIANTS[Tariff.ROOM] == 3
    assert TARIFF_VARIANTS[Tariff.PRO_ROOM] == 4


# ─── Prompt building ──────────────────────────────────────────────────────────

def test_prompt_build():
    from app.integrations.ai.client import build_image_prompt, build_negative_prompt
    from unittest.mock import MagicMock

    project = MagicMock()
    project.id = 1
    project.room_type = "living"
    project.style = "japandi"
    project.budget_tier = "medium"
    project.area_m2 = 20.0
    project.free_space_percent = "40"
    project.ceiling_height = 2.7
    project.keep_items = "диван"
    project.remove_items = None
    project.extra_notes = "больше света"

    prompt = build_image_prompt(project)
    assert "japandi" in prompt
    assert "living room" in prompt
    assert "20.0 square meters" in prompt
    assert "больше света" in prompt

    neg = build_negative_prompt()
    assert "blurry" in neg
    assert "distorted" in neg


# ─── Watermark ────────────────────────────────────────────────────────────────

def test_watermark_returns_bytes():
    from app.utils.watermark import add_watermark
    from PIL import Image
    import io

    # Create a small test image
    img = Image.new("RGB", (100, 100), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    original_bytes = buf.getvalue()

    result = add_watermark(original_bytes, text="Test")
    assert isinstance(result, bytes)
    assert len(result) > 0


# ─── Shopping list builder ────────────────────────────────────────────────────

def test_shopping_list_build():
    from app.services.generation.service import build_shopping_list
    from unittest.mock import MagicMock

    project = MagicMock()
    project.style = "japandi"
    project.budget_tier = "medium"

    result = build_shopping_list(project)
    assert "items" in result
    assert len(result["items"]) > 0
    assert "category" in result["items"][0]


def test_shopping_list_fallback():
    from app.services.generation.service import build_shopping_list
    from unittest.mock import MagicMock

    project = MagicMock()
    project.style = "unknown_style_xyz"
    project.budget_tier = "minimal"

    result = build_shopping_list(project)
    assert "items" in result
    assert len(result["items"]) > 0


# ─── Concept text builder ─────────────────────────────────────────────────────

def test_concept_text():
    from app.services.generation.service import build_concept_text
    from unittest.mock import MagicMock

    project = MagicMock()
    project.style = "scandinavian"
    project.budget_tier = "medium"
    project.free_space_percent = "50"
    project.extra_notes = "уютно и светло"

    text = build_concept_text(project)
    assert "Скандинавский" in text
    assert "50%" in text
    assert "уютно и светло" in text


# ─── FSM states existence ─────────────────────────────────────────────────────

def test_fsm_states_exist():
    from app.bot.states.states import ProjectForm, PaymentFlow, AdminFlow

    assert hasattr(ProjectForm, "room_type")
    assert hasattr(ProjectForm, "area")
    assert hasattr(ProjectForm, "style")
    assert hasattr(ProjectForm, "photos")
    assert hasattr(ProjectForm, "confirmation")
    assert hasattr(PaymentFlow, "tariff_selection")
    assert hasattr(PaymentFlow, "waiting_payment")
    assert hasattr(AdminFlow, "waiting_broadcast_text")
