import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from app.core.config import settings
from app.core.logging import setup_logging
from app.bot.middlewares.auth import AuthMiddleware
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.bot.handlers import start, project, payment, my_projects, admin


async def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def create_dispatcher() -> Dispatcher:
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    # Middlewares (order matters)
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Routers
    dp.include_router(start.router)
    dp.include_router(project.router)
    dp.include_router(payment.router)
    dp.include_router(my_projects.router)
    dp.include_router(admin.router)

    return dp


async def run_polling():
    """Run bot in long-polling mode (development)."""
    setup_logging()
    bot = await create_bot()
    dp = await create_dispatcher()

    logger.info("Starting bot in polling mode...")
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


async def run_webhook():
    """Run bot via webhook (production)."""
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    setup_logging()
    bot = await create_bot()
    dp = await create_dispatcher()

    await bot.set_webhook(
        url=settings.webhook_url,
        drop_pending_updates=True,
    )

    app = web.Application()
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    logger.info(f"Starting webhook on {settings.webhook_url}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

    # Keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run_polling())
