from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from app.db.models import RoomType, InteriorStyle, BudgetTier, FreeSpace, Tariff, ProjectStatus


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🏠 Создать проект"),
        KeyboardButton(text="📁 Мои проекты"),
    )
    builder.row(
        KeyboardButton(text="💰 Тарифы"),
        KeyboardButton(text="🖼 Примеры"),
        KeyboardButton(text="❓ Помощь"),
    )
    return builder.as_markup(resize_keyboard=True)


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


# ─── Project form ─────────────────────────────────────────────────────────────

def room_type_keyboard() -> InlineKeyboardMarkup:
    room_labels = {
        RoomType.KITCHEN: "🍳 Кухня",
        RoomType.BEDROOM: "🛏 Спальня",
        RoomType.LIVING: "🛋 Гостиная",
        RoomType.KIDS: "🧸 Детская",
        RoomType.BATHROOM: "🚿 Ванная",
        RoomType.OFFICE: "💻 Кабинет",
        RoomType.HALLWAY: "🚪 Прихожая",
        RoomType.OTHER: "📦 Другое",
    }
    builder = InlineKeyboardBuilder()
    for room, label in room_labels.items():
        builder.button(text=label, callback_data=f"room:{room.value}")
    builder.adjust(2)
    return builder.as_markup()


def style_keyboard() -> InlineKeyboardMarkup:
    style_labels = {
        InteriorStyle.JAPANDI: "🍃 Джапанди",
        InteriorStyle.MINIMALISM: "⬜ Минимализм",
        InteriorStyle.MODERN: "🏙 Современный",
        InteriorStyle.SCANDINAVIAN: "❄️ Скандинавский",
        InteriorStyle.LOFT: "🏭 Лофт",
        InteriorStyle.NEOCLASSIC: "🏛 Неоклассика",
        InteriorStyle.COZY_LIGHT: "☀️ Светлый уютный",
    }
    builder = InlineKeyboardBuilder()
    for style, label in style_labels.items():
        builder.button(text=label, callback_data=f"style:{style.value}")
    builder.adjust(2)
    return builder.as_markup()


def budget_keyboard() -> InlineKeyboardMarkup:
    budget_labels = {
        BudgetTier.MINIMAL: "💸 Минимальный",
        BudgetTier.MEDIUM: "💰 Средний",
        BudgetTier.ABOVE_MEDIUM: "💎 Выше среднего",
        BudgetTier.PREMIUM: "👑 Премиум",
    }
    builder = InlineKeyboardBuilder()
    for budget, label in budget_labels.items():
        builder.button(text=label, callback_data=f"budget:{budget.value}")
    builder.adjust(2)
    return builder.as_markup()


def free_space_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for space in FreeSpace:
        builder.button(text=f"{space.value}%", callback_data=f"space:{space.value}")
    builder.adjust(4)
    return builder.as_markup()


def skip_keyboard(step: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить", callback_data=f"skip:{step}")
    return builder.as_markup()


def photos_done_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово (загрузить)", callback_data="photos:done")
    builder.button(text="❌ Отменить проект", callback_data="project:cancel")
    builder.adjust(1)
    return builder.as_markup()


def confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Запустить генерацию", callback_data="confirm:start")
    builder.button(text="✏️ Изменить параметры", callback_data="confirm:edit")
    builder.button(text="❌ Отменить", callback_data="project:cancel")
    builder.adjust(1)
    return builder.as_markup()


# ─── Tariff / payment ─────────────────────────────────────────────────────────

def tariff_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🆓 Бесплатный preview", callback_data="tariff:free")
    builder.button(text="🏠 Room — 499₽", callback_data="tariff:room")
    builder.button(text="⭐ Pro Room — 999₽", callback_data="tariff:pro_room")
    builder.button(text="🏢 Flat — 1999₽", callback_data="tariff:flat")
    builder.button(text="🏷 Realtor Pack — 2999₽", callback_data="tariff:realtor_pack")
    builder.adjust(1)
    return builder.as_markup()


def payment_keyboard(invoice_url: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if invoice_url:
        builder.button(text="💳 Оплатить", url=invoice_url)
    builder.button(text="❌ Отмена", callback_data="payment:cancel")
    builder.adjust(1)
    return builder.as_markup()


# ─── Post-result ──────────────────────────────────────────────────────────────

def result_keyboard(has_free_plan: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Ещё вариант", callback_data="result:retry")
    builder.button(text="🎨 Сменить стиль", callback_data="result:change_style")
    builder.button(text="➕ Новый проект", callback_data="result:new_project")
    if has_free_plan:
        builder.button(text="💎 Купить полный пакет", callback_data="result:upgrade")
    builder.button(text="📁 Мои проекты", callback_data="result:my_projects")
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup()


# ─── Project list ─────────────────────────────────────────────────────────────

def project_actions_keyboard(project_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == ProjectStatus.DONE:
        builder.button(text="👁 Посмотреть результат", callback_data=f"proj_view:{project_id}")
        builder.button(text="🔄 Повторить генерацию", callback_data=f"proj_retry:{project_id}")
    builder.button(text="🗑 Удалить", callback_data=f"proj_delete:{project_id}")
    builder.adjust(1)
    return builder.as_markup()


# ─── Admin ────────────────────────────────────────────────────────────────────

def admin_project_keyboard(project_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Перезапустить генерацию", callback_data=f"admin_retry:{project_id}")
    builder.button(text="✅ Пометить как готово", callback_data=f"admin_done:{project_id}")
    builder.button(text="❌ Отменить проект", callback_data=f"admin_cancel:{project_id}")
    builder.adjust(1)
    return builder.as_markup()
