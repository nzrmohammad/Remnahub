from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from aiogram import Bot

from bot.config import settings
from bot.db.engine import engine
from bot.db.base import Base
from bot.db.models import User, UserStatsCache
from bot.keyboards.inline import main_menu_kb
from bot.remnawave.client import remnawave
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

NOTIFICATION_INTERVAL_MINUTES = 60


def format_bytes(bytes_val: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} PB"


async def _send_notification(bot: Bot, user: User, cache: UserStatsCache, lang: str) -> None:
    from bot.keyboards.inline import InlineKeyboardMarkup, InlineKeyboardButton

    used = cache.used_traffic_bytes or 0
    total = cache.total_traffic_bytes or 0

    if total > 0:
        usage_percent = (used / total) * 100

        if usage_percent >= 90 and user.volume_warning_enabled:
            used_gb = round(used / (1024**3), 2)
            total_gb = round(total / (1024**3), 2)

            if lang == "fa":
                text = (
                    f"⚠️ <b>هشدار مصرف حجم!</b>\n\n"
                    f"شما {used_gb} GB از {total_gb} GB حجم خود را استفاده کرده‌اید "
                    f"({usage_percent:.1f}%)\n\n"
                    f"برای تمدید بسته حجمی، دکمه زیر را لمس کنید:"
                )
            else:
                text = (
                    f"⚠️ <b>Volume Usage Warning!</b>\n\n"
                    f"You have used {used_gb} GB of {total_gb} GB "
                    f"({usage_percent:.1f}%)\n\n"
                    f"Tap the button below to renew your package:"
                )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="💰 کیف پول", callback_data="menu:wallet"),
                        InlineKeyboardButton(text="📦 بسته ها", callback_data="packages:back"),
                    ],
                    [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="menu:main")],
                ]
            )

            try:
                await bot.send_message(
                    chat_id=user.telegram_id, text=text, reply_markup=kb, parse_mode="HTML"
                )
                logger.info(f"Sent volume warning to user {user.telegram_id}")
            except Exception as e:
                logger.error(f"Failed to send volume warning to {user.telegram_id}: {e}")

    if cache.expire_at:
        try:
            expire_time = datetime.fromisoformat(cache.expire_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            days_left = (expire_time - now).days

            if 0 <= days_left < 2 and user.expiry_warning_enabled:
                if lang == "fa":
                    text = (
                        f"⏰ <b>هشدار انقضا!</b>\n\n"
                        f"کاربر گرامی، تنها <b>{days_left} روز</b> از اشتراک شما باقی مانده است.\n\n"
                        f"برای تمدید اشتراک، دکمه زیر را لمس کنید:"
                    )
                else:
                    text = (
                        f"⏰ <b>Expiry Warning!</b>\n\n"
                        f"Dear user, you have only <b>{days_left} day(s)</b> left on your subscription.\n\n"
                        f"Tap the button below to renew your subscription:"
                    )

                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(text="💰 کیف پول", callback_data="menu:wallet"),
                            InlineKeyboardButton(text="📦 بسته ها", callback_data="packages:back"),
                        ],
                        [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="menu:main")],
                    ]
                )

                try:
                    await bot.send_message(
                        chat_id=user.telegram_id, text=text, reply_markup=kb, parse_mode="HTML"
                    )
                    logger.info(f"Sent expiry warning to user {user.telegram_id}")
                except Exception as e:
                    logger.error(f"Failed to send expiry warning to {user.telegram_id}: {e}")

        except Exception as e:
            logger.error(f"Failed to parse expire_at for user {user.telegram_id}: {e}")


async def _check_user_notifications(bot: Bot, session: AsyncSession) -> None:
    result = await session.execute(select(User).where(User.remnawave_uuid.isnot(None)))
    users = result.scalars().all()

    logger.info(f"Starting notification check for {len(users)} users")

    for user in users:
        if not user.remnawave_uuid:
            continue

        try:
            result = await session.execute(
                select(UserStatsCache).where(UserStatsCache.uuid == user.remnawave_uuid)
            )
            cache = result.scalar_one_or_none()

            if cache:
                await _send_notification(bot, user, cache, user.lang)

        except Exception as e:
            logger.error(f"Failed to check notifications for {user.telegram_id}: {e}")
            continue

    logger.info("Notification check completed")


async def start_notification_task(bot: Bot) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    while True:
        try:
            async with session_factory() as session:
                await _check_user_notifications(bot, session)
        except Exception as e:
            logger.error(f"Notification check error: {e}")

        await asyncio.sleep(NOTIFICATION_INTERVAL_MINUTES * 60)
