from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.db.models import User
from app.bot.messages import (
    WELCOME, HELP_TEXT, EXAMPLES_TEXT, PRICING_TEXT,
)
from app.bot.keyboards.keyboards import main_menu_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db_user: User):
    await state.clear()
    await message.answer(
        WELCOME,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("examples"))
@router.message(F.text == "🖼 Примеры")
async def cmd_examples(message: Message):
    await message.answer(EXAMPLES_TEXT, parse_mode="HTML", disable_web_page_preview=False)


@router.message(Command("pricing"))
@router.message(F.text == "💰 Тарифы")
async def cmd_pricing(message: Message):
    await message.answer(PRICING_TEXT, parse_mode="HTML")
