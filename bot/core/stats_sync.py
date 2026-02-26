from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from bot.config import settings
from bot.db.engine import engine
from bot.db.base import Base
from bot.db.models import User, UserStatsCache
from bot.remnawave.client import remnawave
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

SYNC_INTERVAL_MINUTES = 60


async def _sync_user_stats(session: AsyncSession) -> None:
    result = await session.execute(select(User).where(User.remnawave_uuid.isnot(None)))
    users = result.scalars().all()

    logger.info(f"Starting stats sync for {len(users)} users")

    for user in users:
        if not user.remnawave_uuid:
            continue

        try:
            data = await remnawave.get_user_stats(user.remnawave_uuid)
            if data:
                resp = data.get("response", data)
                user_traffic = resp.get("userTraffic", {})

                used_bytes = user_traffic.get("usedTrafficBytes", 0) or 0
                total_bytes = resp.get("trafficLimitBytes", 0) or 0
                remaining_bytes = max(0, total_bytes - used_bytes) if total_bytes > 0 else 0

                result = await session.execute(
                    select(UserStatsCache).where(UserStatsCache.uuid == user.remnawave_uuid)
                )
                cache = result.scalar_one_or_none()

                if cache:
                    cache.used_traffic_bytes = used_bytes
                    cache.total_traffic_bytes = total_bytes
                    cache.remaining_traffic_bytes = remaining_bytes
                    cache.status = resp.get("status", "UNKNOWN")
                    cache.expire_at = resp.get("expireAt")
                    cache.online_at = user_traffic.get("onlineAt")
                    cache.updated_at = datetime.now(timezone.utc)
                else:
                    cache = UserStatsCache(
                        uuid=user.remnawave_uuid,
                        username=resp.get("username"),
                        status=resp.get("status", "UNKNOWN"),
                        used_traffic_bytes=used_bytes,
                        total_traffic_bytes=total_bytes,
                        remaining_traffic_bytes=remaining_bytes,
                        expire_at=resp.get("expireAt"),
                        online_at=user_traffic.get("onlineAt"),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(cache)

                await session.commit()

        except Exception as e:
            logger.error(f"Failed to sync stats for {user.remnawave_uuid}: {e}")
            continue

    logger.info("Stats sync completed")


async def start_stats_sync_task() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    while True:
        try:
            async with session_factory() as session:
                await _sync_user_stats(session)
        except Exception as e:
            logger.error(f"Stats sync error: {e}")

        await asyncio.sleep(SYNC_INTERVAL_MINUTES * 60)
