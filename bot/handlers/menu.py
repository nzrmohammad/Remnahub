from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.core.i18n import t
from bot.db.models.user import User
from bot.keyboards.inline import (
    main_menu_kb,
    back_to_menu_kb,
    lang_select_kb,
    settings_kb,
    account_list_kb,
    account_detail_kb,
)
from bot.config import settings as cfg
from bot.remnawave.client import remnawave
from bot.utils.date import to_persian_date, days_until_persian

router = Router(name="menu")


async def _get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


# ── Back to main menu ──────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:back")
async def cb_menu_back(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await call.message.edit_text(
        t(lang, "menu_welcome"),
        reply_markup=main_menu_kb(lang),
    )


# ── Quick Stats ────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user or not user.remnawave_uuid:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(t(lang, "stats_loading"), reply_markup=back_to_menu_kb(lang))
    data = await remnawave.get_user_stats(user.remnawave_uuid)

    if data:
        resp = data.get("response", data)
        user_traffic = resp.get("userTraffic", {})

        used_bytes = user_traffic.get("usedTrafficBytes", 0) or 0
        total_bytes = resp.get("trafficLimitBytes", 0) or 0
        remaining_bytes = max(0, total_bytes - used_bytes) if total_bytes > 0 else 0

        used_gb = round(used_bytes / 1e9, 2)
        total_gb = round(total_bytes / 1e9, 2) if total_bytes > 0 else "∞"
        remaining_gb = round(remaining_bytes / 1e9, 2)

        expire_at = resp.get("expireAt")
        expire_display = "—"
        if expire_at:
            expire_date = expire_at[:10]
            try:
                days_left = days_until_persian(expire_at)
                persian_expire = to_persian_date(expire_date)
                expire_display = f"{persian_expire} ({days_left} روز)"
            except Exception:
                expire_display = expire_date

        status = resp.get("status", "—")
        status_fa = {"ACTIVE": "✅ فعال", "DISABLED": "❌ غیرفعال", "EXPIRED": "⏰ منقضی"}.get(
            status, status
        )

        online_at = user_traffic.get("onlineAt")
        last_connection = to_persian_date(online_at[:19], include_time=True) if online_at else "—"

        text = (
            f"👤 <b>{'نام' if lang == 'fa' else 'Name'}</b>: {resp.get('username', '—')} ({status_fa})\n"
            f"──────────────────\n"
            f"🗂️ <b>{'حجم کل' if lang == 'fa' else 'Total'}</b>: {total_gb} GB\n"
            f"🔥 <b>{'حجم مصرف شده' if lang == 'fa' else 'Used'}</b>: {used_gb} GB\n"
            f"📥 <b>{'حجم باقیمانده' if lang == 'fa' else 'Remaining'}</b>: {remaining_gb} GB\n"
            f"⚡️ <b>{'مصرف امروز' if lang == 'fa' else 'Today'}</b>: 0 MB\n"
            f"⏰ <b>{'آخرین اتصال' if lang == 'fa' else 'Last Connection'}</b>: {last_connection}\n"
            f"📅 <b>{'انقضا' if lang == 'fa' else 'Expiry'}</b>: {expire_display}\n"
            f"🔑 <b>{'شناسه کاربری' if lang == 'fa' else 'User ID'}</b>: <code>{user.remnawave_uuid}</code>"
        )
    else:
        text = t(lang, "no_data")

    await call.message.edit_text(text, reply_markup=back_to_menu_kb(lang), parse_mode="HTML")


# ── Account Management ─────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:account")
async def cb_account(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user or not user.remnawave_uuid:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    data = await remnawave.get_user_stats(user.remnawave_uuid)
    resp = data.get("response", data) if data else {}

    accounts = [
        {
            "username": resp.get("username", "—"),
            "uuid": user.remnawave_uuid,
            "status": resp.get("status", "UNKNOWN"),
        }
    ]

    text = f"👤 <b>{'مدیریت اکانت' if lang == 'fa' else 'Account Management'}</b>\n\n{'یک اکانت یافت شد' if lang == 'fa' else 'One account found'}:"
    await call.message.edit_text(
        text, reply_markup=account_list_kb(accounts, lang), parse_mode="HTML"
    )


@router.callback_query(F.data == "account:list")
async def cb_account_list(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user or not user.remnawave_uuid:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    data = await remnawave.get_user_stats(user.remnawave_uuid)
    resp = data.get("response", data) if data else {}

    accounts = [
        {
            "username": resp.get("username", "—"),
            "uuid": user.remnawave_uuid,
            "status": resp.get("status", "UNKNOWN"),
        }
    ]

    text = f"👤 <b>{'مدیریت اکانت' if lang == 'fa' else 'Account Management'}</b>\n\n{'یک اکانت یافت شد' if lang == 'fa' else 'One account found'}:"
    await call.message.edit_text(
        text, reply_markup=account_list_kb(accounts, lang), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("account:"))
async def cb_account_detail(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    data_parts = call.data.split(":")
    action = data_parts[1] if len(data_parts) > 1 else ""

    if action == "link":
        uuid = data_parts[2] if len(data_parts) > 2 else ""
        await call.message.edit_text(
            f"🔗 <b>{'دریافت لینک' if lang == 'fa' else 'Get Link'}</b>\n\n{'به زودی...' if lang == 'fa' else 'Coming soon...'}",
            reply_markup=account_detail_kb(uuid, lang),
            parse_mode="HTML",
        )
        return
    elif action == "payment":
        uuid = data_parts[2] if len(data_parts) > 2 else ""
        await call.message.edit_text(
            f"💳 <b>{'سابقه پرداخت' if lang == 'fa' else 'Payment History'}</b>\n\n{'به زودی...' if lang == 'fa' else 'Coming soon...'}",
            reply_markup=account_detail_kb(uuid, lang),
            parse_mode="HTML",
        )
        return

    uuid = data_parts[1] if len(data_parts) > 1 else ""
    if not uuid:
        uuid = user.remnawave_uuid if user else ""

    if not uuid:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(t(lang, "stats_loading"), reply_markup=back_to_menu_kb(lang))
    data = await remnawave.get_user_stats(uuid)

    if data:
        resp = data.get("response", data)
        user_traffic = resp.get("userTraffic", {})

        used_bytes = user_traffic.get("usedTrafficBytes", 0) or 0
        total_bytes = resp.get("trafficLimitBytes", 0) or 0
        remaining_bytes = max(0, total_bytes - used_bytes) if total_bytes > 0 else 0

        used_gb = round(used_bytes / 1e9, 2)
        total_gb = round(total_bytes / 1e9, 2) if total_bytes > 0 else "∞"
        remaining_gb = round(remaining_bytes / 1e9, 2)

        expire_at = resp.get("expireAt")
        expire_display = "—"
        if expire_at:
            expire_date = expire_at[:10]
            try:
                days_left = days_until_persian(expire_at)
                persian_expire = to_persian_date(expire_date)
                expire_display = f"{persian_expire} ({days_left} روز)"
            except Exception:
                expire_display = expire_date

        status = resp.get("status", "—")
        status_fa = {"ACTIVE": "✅ فعال", "DISABLED": "❌ غیرفعال", "EXPIRED": "⏰ منقضی"}.get(
            status, status
        )

        online_at = user_traffic.get("onlineAt")
        last_connection = to_persian_date(online_at[:19], include_time=True) if online_at else "—"

        text = (
            f"👤 <b>{'نام' if lang == 'fa' else 'Name'}</b>: {resp.get('username', '—')} ({status_fa})\n"
            f"──────────────────\n"
            f"🗂️ <b>{'حجم کل' if lang == 'fa' else 'Total'}</b>: {total_gb} GB\n"
            f"🔥 <b>{'حجم مصرف شده' if lang == 'fa' else 'Used'}</b>: {used_gb} GB\n"
            f"📥 <b>{'حجم باقیمانده' if lang == 'fa' else 'Remaining'}</b>: {remaining_gb} GB\n"
            f"⚡️ <b>{'مصرف امروز' if lang == 'fa' else 'Today'}</b>: 0 MB\n"
            f"⏰ <b>{'آخرین اتصال' if lang == 'fa' else 'Last Connection'}</b>: {last_connection}\n"
            f"📅 <b>{'انقضا' if lang == 'fa' else 'Expiry'}</b>: {expire_display}\n"
            f"🔑 <b>{'شناسه کاربری' if lang == 'fa' else 'User ID'}</b>: <code>{uuid}</code>"
        )
    else:
        text = t(lang, "no_data")

    await call.message.edit_text(
        text, reply_markup=account_detail_kb(uuid, lang), parse_mode="HTML"
    )


# ── Wallet ─────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:wallet")
async def cb_wallet(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    text = f"💰 <b>{'کیف پول' if lang == 'fa' else 'Wallet'}</b>\n\n🔧 {'به زودی...' if lang == 'fa' else 'Coming soon...'}"
    await call.message.edit_text(text, reply_markup=back_to_menu_kb(lang), parse_mode="HTML")


# ── Services ───────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:services")
async def cb_services(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user or not user.remnawave_uuid:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(t(lang, "services_loading"), reply_markup=back_to_menu_kb(lang))
    items = await remnawave.get_user_services(user.remnawave_uuid)

    if items:
        lines = [f"📡 <b>{'سرویس‌ها' if lang == 'fa' else 'Services'}</b>\n"]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item.get('name', '—')} — {item.get('protocol', '—')}")
        text = "\n".join(lines)
    else:
        text = f"📡 {'سرویسی یافت نشد' if lang == 'fa' else 'No services found.'}"

    await call.message.edit_text(text, reply_markup=back_to_menu_kb(lang), parse_mode="HTML")


# ── Tutorial ───────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:tutorial")
async def cb_tutorial(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await call.message.edit_text(t(lang, "tutorial_text"), reply_markup=back_to_menu_kb(lang))


# ── Settings ───────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:settings")
async def cb_settings(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await call.message.edit_text(t(lang, "settings_title"), reply_markup=settings_kb(lang))


@router.callback_query(F.data == "settings:change_lang")
async def cb_change_lang(call: CallbackQuery, session: AsyncSession) -> None:
    await call.answer()
    await call.message.edit_text(
        t("en", "lang_select_title"),
        reply_markup=lang_select_kb(),
    )


# ── Support ────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:support")
async def cb_support(call: CallbackQuery, session: AsyncSession) -> None:
    from bot.states.fsm import Support
    from aiogram.fsm.context import FSMContext

    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await call.message.edit_text(t(lang, "support_prompt"), reply_markup=back_to_menu_kb(lang))


# ── Profile ────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:profile")
async def cb_profile(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    text = (
        f"🧑‍💼 <b>{'حساب کاربری' if lang == 'fa' else 'My Profile'}</b>\n\n"
        f"• {'نام' if lang == 'fa' else 'Name'}: {user.full_name or '—'}\n"
        f"• {'نام کاربری' if lang == 'fa' else 'Username'}: @{user.username or '—'}\n"
        f"• Telegram ID: <code>{call.from_user.id}</code>\n"
        f"• {'زبان' if lang == 'fa' else 'Language'}: {'فارسی 🇮🇷' if lang == 'fa' else 'English 🇬🇧'}\n"
        f"• {'ثبت‌نام' if lang == 'fa' else 'Registered'}: {'✅' if user.is_registered else '❌'}"
    )
    await call.message.edit_text(text, reply_markup=back_to_menu_kb(lang), parse_mode="HTML")


# ── Admin Panel ────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:panel")
async def cb_panel(call: CallbackQuery, session: AsyncSession) -> None:
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖥️ Open Panel",
                    url=cfg.remnawave_api_url,
                )
            ],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:back")],
        ]
    )
    await call.message.edit_text(
        f"🖥️ {'پنل مدیریت' if lang == 'fa' else 'Admin Panel'}",
        reply_markup=kb,
    )
