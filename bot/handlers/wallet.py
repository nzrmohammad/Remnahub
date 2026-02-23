from __future__ import annotations

import uuid as uuid_lib
import asyncio

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from bot.config import settings
from bot.core.i18n import t
from bot.db.models.user import User
from bot.keyboards.inline import (
    wallet_main_kb,
    wallet_cancel_kb,
    wallet_payment_kb,
    wallet_success_kb,
    back_to_menu_kb,
    admin_approve_reject_kb,
)
from bot.states.fsm import Wallet

log = structlog.get_logger()
router = Router(name="wallet")

pending_requests: dict[str, dict] = {}


async def _get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def _get_user_balance(telegram_id: int) -> int:
    return 0


@router.callback_query(F.data == "menu:wallet")
async def cb_wallet(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await state.set_state(Wallet.idle)

    balance = await _get_user_balance(call.from_user.id)
    balance_text = f"{balance:,}"

    text = (
        f"💰 <b>{'کیف پول' if lang == 'fa' else 'Wallet'}</b>\n\n"
        f"💵 {'موجودی شما' if lang == 'fa' else 'Your Balance'}: <b>{balance_text} تومان</b>"
    )
    await call.message.edit_text(
        text,
        reply_markup=wallet_main_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "wallet:balance")
async def cb_wallet_balance(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    balance = await _get_user_balance(call.from_user.id)
    balance_text = f"{balance:,}"

    text = (
        f"💰 <b>{'کیف پول' if lang == 'fa' else 'Wallet'}</b>\n\n"
        f"💵 {'موجودی شما' if lang == 'fa' else 'Your Balance'}: <b>{balance_text} تومان</b>"
    )
    await call.message.edit_text(
        text,
        reply_markup=wallet_main_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "wallet:history")
async def cb_wallet_history(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    text = f"📜 <b>{'تاریخچه تراکنش‌ها' if lang == 'fa' else 'Transaction History'}</b>\n\n{'به زودی...' if lang == 'fa' else 'Coming soon...'}"
    await call.message.edit_text(
        text,
        reply_markup=back_to_menu_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "wallet:charge")
async def cb_wallet_charge(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await state.set_state(Wallet.waiting_for_amount)

    text = (
        f"💰 <b>{'شارژ حساب' if lang == 'fa' else 'Charge Account'}</b>\n\n"
        f"{'لطفاً مبلغی که می‌خواهید کیف پول خود را شارژ کنید (به تومان) وارد نمایید:' if lang == 'fa' else 'Please enter the amount you want to charge (in Toman):'}\n\n"
        f"{'مثال: 50000' if lang == 'fa' else 'Example: 50000'}"
    )
    await call.message.edit_text(
        text,
        reply_markup=wallet_cancel_kb(lang),
        parse_mode="HTML",
    )


@router.message(Wallet.waiting_for_amount)
async def handle_wallet_amount(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    try:
        amount = int(message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError()
    except Exception:
        await message.answer(
            t(lang, "invalid_amount")
            if hasattr(t(lang), "__call__")
            else "لطفاً مبلغ معتبر وارد کنید.",
            reply_markup=wallet_cancel_kb(lang),
        )
        return

    await message.delete()

    request_id = str(uuid_lib.uuid4())[:8]
    amount_text = f"{amount:,}"

    pending_requests[request_id] = {
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "full_name": message.from_user.full_name,
        "amount": amount,
        "lang": lang,
    }

    await state.update_data(wallet_request_id=request_id, wallet_amount=amount)
    await state.set_state(Wallet.waiting_for_receipt)

    text = (
        f"💳 <b>{'اطلاعات پرداخت' if lang == 'fa' else 'Payment Information'}</b>\n\n"
        f"{'لطفاً مبلغ' if lang == 'fa' else 'Please pay'} <b>{amount_text} تومان</b> "
        f"{'به کارت زیر واریز کرده و سپس از رسید پرداخت اسکرین‌شات گرفته و آن را در همین صفحه ارسال کنید.' if lang == 'fa' else 'to the card below and then send a screenshot of the payment receipt in this chat.'}\n\n"
        f"🏦 {settings.payment_card_holder}\n"
        f"💳 <code>{settings.payment_card_number}</code>\n\n"
        f"⚠️ {'توجه: پس از ارسال رسید، باید منتظر تایید ادمین بمانید.' if lang == 'fa' else 'Note: After sending the receipt, you must wait for admin approval.'}"
    )
    await message.answer(
        text,
        reply_markup=wallet_payment_kb(lang),
        parse_mode="HTML",
    )


@router.message(Wallet.waiting_for_receipt, F.photo)
async def handle_wallet_receipt(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"
    data = await state.get_data()
    request_id = data.get("wallet_request_id", "unknown")
    amount = data.get("wallet_amount", 0)

    await message.delete()

    balance = await _get_user_balance(message.from_user.id)
    balance_text = f"{balance:,}"
    amount_text = f"{amount:,}"

    user_link = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else f"tg://user?id={message.from_user.id}"
    )

    admin_text = (
        f"💸 <b>{'درخواست شارژ کیف پول جدید' if lang == 'fa' else 'New Wallet Charge Request'}</b>\n"
        f"🆔 {'شناسه درخواست' if lang == 'fa' else 'Request ID'}: <code>{request_id}</code>\n\n"
        f"👤 {'نام کاربر' if lang == 'fa' else 'User'}: {message.from_user.full_name}\n"
        f"🆔 {'ایدی' if lang == 'fa' else 'ID'}: <code>{message.from_user.id}</code>\n"
        f"🔗 {'یوزرنیم' if lang == 'fa' else 'Username'}: {user_link}\n"
        f"💰 {'موجودی فعلی' if lang == 'fa' else 'Current Balance'}: {balance_text} {'تومان' if lang == 'fa' else 'Toman'}\n\n"
        f"💳 {'مبلغ درخواستی' if lang == 'fa' else 'Requested Amount'}: {amount_text} {'تومان' if lang == 'fa' else 'Toman'}"
    )

    try:
        photo = message.photo[-1]
        await bot.send_photo(
            chat_id=settings.admin_group_id,
            message_thread_id=settings.payment_receipts_topic_id,
            photo=photo.file_id,
            caption=admin_text,
            reply_markup=admin_approve_reject_kb(request_id),
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("Failed to send receipt to admin", error=str(e))
        await message.answer(
            t(lang, "error_occurred")
            if hasattr(t(lang), "__call__")
            else "خطایی رخ داد. لطفاً دوباره تلاش کنید.",
            reply_markup=back_to_menu_kb(lang),
        )
        return

    await state.clear()
    await state.set_state(Wallet.idle)

    await message.answer(
        f"✅ {'رسید شما دریافت شد. پس از تایید توسط ادمین، حساب شما شارژ خواهد شد.' if lang == 'fa' else '✅ Your receipt has been received. After admin approval, your account will be charged.'}",
        reply_markup=back_to_menu_kb(lang),
        parse_mode="HTML",
    )


@router.message(Wallet.waiting_for_receipt)
async def handle_wallet_receipt_invalid(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    await message.delete()
    await message.answer(
        f"⚠️ {'لطفاً فقط تصویر رسید پرداخت را ارسال کنید.' if lang == 'fa' else 'Please only send the payment receipt image.'}",
        reply_markup=wallet_payment_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "wallet:cancel")
async def cb_wallet_cancel(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await state.clear()
    await state.set_state(Wallet.idle)

    balance = await _get_user_balance(call.from_user.id)
    balance_text = f"{balance:,}"

    text = (
        f"💰 <b>{'کیف پول' if lang == 'fa' else 'Wallet'}</b>\n\n"
        f"💵 {'موجودی شما' if lang == 'fa' else 'Your Balance'}: <b>{balance_text} تومان</b>"
    )
    await call.message.edit_text(
        text,
        reply_markup=wallet_main_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("wallet:approve:"))
async def cb_wallet_approve(call: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if call.from_user.id not in settings.admin_ids:
        await call.answer()
        return

    request_id = call.data.split(":")[-1]
    await call.answer()

    if request_id not in pending_requests:
        await call.message.edit_text(
            "درخواست یافت نشد.",
            parse_mode="HTML",
        )
        return

    request_data = pending_requests.pop(request_id)
    user_id = request_data["user_id"]
    amount = request_data["amount"]
    lang = request_data["lang"]

    amount_text = f"{amount:,}"

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"✅ {'حساب شما به مبلغ' if lang == 'fa' else 'Your account has been charged with'} {amount_text} {'تومان با موفقیت شارژ شد.' if lang == 'fa' else 'Toman successfully.'}\n\n"
            f"{'حالا می‌توانید سرویس مورد نظر خود را از بخش «سرویس‌ها» خریداری یا تمدید کنید.' if lang == 'fa' else 'Now you can purchase or renew your service from the Services section.'}",
            reply_markup=wallet_success_kb(lang),
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("Failed to notify user of approval", error=str(e))

    await call.message.edit_text(
        call.message.text + "\n\n✅ <b>تایید شد</b>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("wallet:reject:"))
async def cb_wallet_reject(call: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if call.from_user.id not in settings.admin_ids:
        await call.answer()
        return

    request_id = call.data.split(":")[-1]
    await call.answer()

    if request_id not in pending_requests:
        await call.message.edit_text(
            "درخواست یافت نشد.",
            parse_mode="HTML",
        )
        return

    request_data = pending_requests.pop(request_id)
    user_id = request_data["user_id"]
    lang = request_data["lang"]

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"❌ {'درخواست شارژ حساب شما توسط ادمین رد شد. لطفاً با پشتیبانی تماس بگیرید.' if lang == 'fa' else '❌ Your charge request was rejected by admin. Please contact support.'}",
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("Failed to notify user of rejection", error=str(e))

    await call.message.edit_text(
        call.message.text + "\n\n❌ <b>رد شد</b>",
        parse_mode="HTML",
    )
