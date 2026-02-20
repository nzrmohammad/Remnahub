from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from bot.config import settings
from bot.core.middlewares.db import DbSessionMiddleware
from bot.handlers import start, auth, menu


def create_dispatcher() -> tuple[Bot, Dispatcher]:
    bot = Bot(token=settings.bot_token)
    storage = RedisStorage(Redis.from_url(settings.redis_url))
    dp = Dispatcher(storage=storage)

    # Register middleware on ALL update types
    dp.update.middleware(DbSessionMiddleware())

    # Register routers in order (most specific first)
    dp.include_router(start.router)
    dp.include_router(auth.router)
    dp.include_router(menu.router)

    return bot, dp
