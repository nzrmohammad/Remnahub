from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.core.i18n import t
from bot.db.models.user import User
from bot.keyboards.inline import lang_select_kb, rules_kb, RULES_TEXT_FA, RULES_TEXT_EN
from bot.states.fsm import AuthMenu

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """Handle /start — show rules first, then language selection."""
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
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

        await state.set_state(AuthMenu.waiting_for_rules)
        await message.answer(
            RULES_TEXT_FA,
            reply_markup=rules_kb("fa"),
            parse_mode="HTML",
        )
    else:
        user.username = message.from_user.username
        user.full_name = message.from_user.full_name
        await session.commit()

        await message.answer(
            t("en", "lang_select_title"),
            reply_markup=lang_select_kb(),
        )


@router.callback_query(lambda c: c.data == "rules:accept")
async def cb_rules_accept(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await call.answer()

    current_state = await state.get_state()
    if current_state == AuthMenu.waiting_for_rules.state:
        await state.set_state(AuthMenu.waiting_for_lang)
        await call.message.edit_text(
            t("fa", "lang_select_title"),
            reply_markup=lang_select_kb(),
        )
    else:
        await call.answer("❌")
