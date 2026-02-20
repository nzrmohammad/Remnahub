from __future__ import annotations

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from bot.config import settings
from bot.core.i18n import t
from bot.db.models.user import User
from bot.keyboards.inline import auth_menu_kb, back_to_auth_kb, main_menu_kb
from bot.remnawave.client import remnawave
from bot.states.fsm import NewService

log = structlog.get_logger()
router = Router(name="auth")


# ── Language selection ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("lang:"))
async def cb_lang_select(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    lang = call.data.split(":")[1]  # "fa" or "en"

    # Save language to DB
    result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
    user = result.scalar_one_or_none()
    if user:
        user.lang = lang
        await session.commit()

    await state.update_data(lang=lang)
    await call.answer()

    # Edit same message → show Login / New Service
    await call.message.edit_text(
        f"🌐 {'زبان فارسی انتخاب شد' if lang == 'fa' else 'English selected'}\n\n"
        + t(lang, "btn_login") + " | " + t(lang, "btn_new_service"),
        reply_markup=auth_menu_kb(lang),
    )


# ── Login flow ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "auth:login")
async def cb_login(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
    user = result.scalar_one_or_none()
    lang = user.lang if user else data.get("lang", "en")

    await call.answer()
    # Edit message to show loading
    await call.message.edit_text(t(lang, "login_checking"))

    # Check Remnawave
    rw_user = await remnawave.get_user_by_telegram_id(call.from_user.id)

    if rw_user:
        # Found — update DB and go to main menu
        if user:
            user.is_registered = True
            user.remnawave_uuid = rw_user.get("uuid")
            await session.commit()

        await call.message.edit_text(
            t(lang, "menu_welcome"),
            reply_markup=main_menu_kb(lang),
        )
    else:
        # Not found
        await call.message.edit_text(
            t(lang, "login_not_found"),
            reply_markup=back_to_auth_kb(lang),
        )


@router.callback_query(F.data == "auth:back")
async def cb_auth_back(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
    user = result.scalar_one_or_none()
    data = await state.get_data()
    lang = user.lang if user else data.get("lang", "en")
    await call.answer()
    await call.message.edit_text(
        f"🌐 {'فارسی' if lang == 'fa' else 'English'}\n\n"
        + t(lang, "btn_login") + " | " + t(lang, "btn_new_service"),
        reply_markup=auth_menu_kb(lang),
    )


# ── New service request ────────────────────────────────────────────────────────

@router.callback_query(F.data == "auth:new_service")
async def cb_new_service(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
    user = result.scalar_one_or_none()
    data = await state.get_data()
    lang = user.lang if user else data.get("lang", "en")
    await call.answer()

    await state.set_state(NewService.waiting_for_info)
    sent = await call.message.edit_text(
        t(lang, "new_service_prompt"),
        reply_markup=back_to_auth_kb(lang),
    )
    # Store the message id so we can edit it after the user replies
    await state.update_data(bot_msg_id=call.message.message_id, lang=lang)


@router.message(NewService.waiting_for_info)
async def handle_new_service_info(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()
    data = await state.get_data()
    lang = user.lang if user else data.get("lang", "en")

    # Delete user's message to keep chat clean
    try:
        await message.delete()
    except Exception:
        pass

    # Forward to admin group topic
    if settings.admin_group_id:
        user_link = f"@{message.from_user.username}" if message.from_user.username else f"tg://user?id={message.from_user.id}"
        admin_text = (
            f"📋 <b>New Service Request</b>\n"
            f"👤 {message.from_user.full_name} ({user_link})\n"
            f"🆔 <code>{message.from_user.id}</code>\n\n"
            f"💬 {message.text}"
        )
        try:
            await bot.send_message(
                chat_id=settings.admin_group_id,
                message_thread_id=settings.admin_topic_id,
                text=admin_text,
                parse_mode="HTML",
            )
        except Exception as e:
            log.error("Failed to send to admin group", error=str(e))

    await state.clear()

    # Edit the bot's previous message back to confirmation + back button
    # We need to find the last bot message in the chat — we use FSM data to store it
    msg_id = data.get("bot_msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text=t(lang, "new_service_sent"),
                reply_markup=back_to_auth_kb(lang),
            )
        except Exception:
            pass
