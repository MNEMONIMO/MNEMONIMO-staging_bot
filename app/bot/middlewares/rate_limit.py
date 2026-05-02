from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
import time
from collections import defaultdict

# In-memory rate limiter (use Redis in production for multi-worker setups)
_rate_store: dict[int, list[float]] = defaultdict(list)

RATE_LIMIT_MESSAGES = 20      # max messages
RATE_LIMIT_WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = None
        if isinstance(event, (Message, CallbackQuery)):
            tg_user = event.from_user

        if not tg_user:
            return await handler(event, data)

        uid = tg_user.id
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW_SECONDS

        # Prune old timestamps
        _rate_store[uid] = [t for t in _rate_store[uid] if t > window_start]

        if len(_rate_store[uid]) >= RATE_LIMIT_MESSAGES:
            if isinstance(event, Message):
                await event.answer("⚠️ Слишком много запросов. Подожди немного.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Слишком много запросов.", show_alert=True)
            return

        _rate_store[uid].append(now)
        return await handler(event, data)
