from __future__ import annotations

import asyncio
import logging
import structlog

from bot.config import settings
from bot.core.dispatcher import create_dispatcher
from bot.core.stats_sync import start_stats_sync_task
from bot.core.user_notifications import start_notification_task
from bot.db.engine import engine
from bot.db.base import Base
from bot.db.models import User, UserStatsCache  # noqa: F401


async def on_startup(bot, dispatcher) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info("Database tables ensured.")

    asyncio.create_task(start_stats_sync_task())
    logging.info("Stats sync task started")

    asyncio.create_task(start_notification_task(bot))
    logging.info("Notification task started")


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
    )

    bot, dp = create_dispatcher()
    dp.startup.register(on_startup)

    logging.info("Starting Remnabot polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
