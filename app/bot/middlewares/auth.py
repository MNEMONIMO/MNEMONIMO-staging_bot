from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from loguru import logger

from app.db.session import AsyncSessionLocal
from app.repositories.user_repository import UserRepository
from app.bot.messages import BLOCKED_USER


class AuthMiddleware(BaseMiddleware):
    """Upserts user on every update and blocks banned accounts."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Extract Telegram user from the event
        tg_user = None
        if isinstance(event, (Message, CallbackQuery)):
            tg_user = event.from_user

        if not tg_user:
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            user, created = await repo.get_or_create(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language_code=tg_user.language_code,
            )
            await session.commit()

            if user.is_blocked:
                if isinstance(event, Message):
                    await event.answer(BLOCKED_USER)
                elif isinstance(event, CallbackQuery):
                    await event.answer(BLOCKED_USER, show_alert=True)
                return

            # Inject user and session into handler data
            data["db_user"] = user
            data["is_new_user"] = created

        if created:
            logger.info(f"New user registered: {tg_user.id} @{tg_user.username}")

        return await handler(event, data)
