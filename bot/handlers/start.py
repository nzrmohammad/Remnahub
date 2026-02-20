from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.core.i18n import t
from bot.db.models.user import User
from bot.keyboards.inline import lang_select_kb

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    """Handle /start — upsert user, show bilingual language selection."""
    # Upsert user in DB
    result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            lang="en",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Update name in case it changed
        user.username = message.from_user.username
        user.full_name = message.from_user.full_name
        await session.commit()

    # Delete the /start message to keep chat clean
    await message.delete()

    # Send language selection (bilingual)
    await message.answer(
        t("en", "lang_select_title"),
        reply_markup=lang_select_kb(),
    )
