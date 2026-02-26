from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from bot.core.i18n import t
from bot.db.models.user import User
from bot.db.models.user_stats_cache import UserStatsCache
from bot.keyboards.inline import (
    main_menu_kb,
    back_to_menu_kb,
    lang_select_kb,
    settings_kb,
    account_list_kb,
    account_detail_kb,
    stats_navigation_kb,
    admin_main_kb,
    admin_users_kb,
    admin_stats_kb,
    admin_user_list_kb,
    tutorial_os_select_kb,
    tutorial_app_select_kb,
    tutorial_view_kb,
    settings_warnings_kb,
)
from bot.config import settings as cfg
from bot.remnawave.client import remnawave
from bot.utils.date import to_persian_date, days_until_persian
from bot.states.fsm import Admin

router = Router(name="menu")


async def _get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def _get_user_stats_from_cache(session: AsyncSession, uuid: str) -> UserStatsCache | None:
    result = await session.execute(select(UserStatsCache).where(UserStatsCache.uuid == uuid))
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


async def _build_stats_text(resp: dict, uuid: str, lang: str, use_cache: bool = False) -> str:
    if use_cache and resp:
        cache = resp
        used_bytes = cache.used_traffic_bytes or 0
        total_bytes = cache.total_traffic_bytes or 0
        remaining_bytes = cache.remaining_traffic_bytes or 0
        username = cache.username
        status = cache.status
        expire_at = cache.expire_at
        online_at = cache.online_at
    else:
        user_traffic = resp.get("userTraffic", {})
        used_bytes = user_traffic.get("usedTrafficBytes", 0) or 0
        total_bytes = resp.get("trafficLimitBytes", 0) or 0
        remaining_bytes = max(0, total_bytes - used_bytes) if total_bytes > 0 else 0
        username = resp.get("username", "—")
        status = resp.get("status", "—")
        expire_at = resp.get("expireAt")
        online_at = user_traffic.get("onlineAt")

    used_gb = round(used_bytes / (1024**3), 2)
    total_gb = round(total_bytes / (1024**3), 2) if total_bytes > 0 else "∞"
    remaining_gb = round(remaining_bytes / (1024**3), 2)

    usage_percent = round((used_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
    progress_bar = _build_progress_bar(usage_percent)

    expire_display = "—"
    if expire_at:
        try:
            days_left = days_until_persian(
                expire_at[:10] if isinstance(expire_at, str) else expire_at
            )
            persian_expire = to_persian_date(
                expire_at[:10] if isinstance(expire_at, str) else expire_at
            )
            expire_display = f"{persian_expire} ({days_left} روز)"
        except Exception:
            expire_display = str(expire_at)[:10] if expire_at else "—"

    status_fa = {"ACTIVE": "✅ فعال", "DISABLED": "❌ غیرفعال", "EXPIRED": "⏰ منقضی"}.get(
        status, status
    )

    last_connection = to_persian_date(online_at, include_time=True) if online_at else "—"

    return (
        f"👤 <b>{'نام' if lang == 'fa' else 'Name'}</b>: {username or '—'} ({status_fa})\n"
        f"──────────────────\n"
        f"🗂️ <b>{'حجم کل' if lang == 'fa' else 'Total'}</b>: {total_gb} GB\n"
        f"🔥 <b>{'حجم مصرف شده' if lang == 'fa' else 'Used'}</b>: {used_gb} GB\n"
        f"📥 <b>{'حجم باقیمانده' if lang == 'fa' else 'Remaining'}</b>: {remaining_gb} GB\n"
        f"⚡️ <b>{'مصرف امروز' if lang == 'fa' else 'Today'}</b>: 0 MB\n"
        f"⏰ <b>{'آخرین اتصال' if lang == 'fa' else 'Last Connection'}</b>: {last_connection}\n"
        f"📅 <b>{'انقضا' if lang == 'fa' else 'Expiry'}</b>: {expire_display}\n"
        f"📊 <b>{'وضعیت' if lang == 'fa' else 'Status'}</b>: {progress_bar} {usage_percent}%\n"
        f"🔑 <b>{'شناسه کاربری' if lang == 'fa' else 'User ID'}</b>: <code>{uuid}</code>"
    )


def _build_progress_bar(percent: float) -> str:
    filled = int(percent / 5)
    empty = 20 - filled
    return "█" * filled + "░" * empty


@router.callback_query(F.data == "menu:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(t(lang, "stats_loading"), reply_markup=back_to_menu_kb(lang))

    all_users = await remnawave.get_all_users_by_telegram_id(call.from_user.id)

    if not all_users or not all_users[0].get("uuid"):
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    uuid = all_users[0].get("uuid")
    cache = await _get_user_stats_from_cache(session, uuid)

    if cache:
        text = await _build_stats_text(cache, uuid, lang, use_cache=True)
    else:
        data = await remnawave.get_user_stats(uuid)
        if data:
            resp = data.get("response", data)
            text = await _build_stats_text(resp, uuid, lang)
        else:
            text = t(lang, "no_data")

    await call.message.edit_text(
        text,
        reply_markup=stats_navigation_kb(0, len(all_users), uuid),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("stats:nav:"))
async def cb_stats_nav(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    index = int(call.data.split(":")[-1])

    all_users = await remnawave.get_all_users_by_telegram_id(call.from_user.id)

    if not all_users or index < 0 or index >= len(all_users):
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(t(lang, "stats_loading"), reply_markup=back_to_menu_kb(lang))

    current_user = all_users[index]
    uuid = current_user.get("uuid")
    cache = await _get_user_stats_from_cache(session, uuid)

    if cache:
        text = await _build_stats_text(cache, uuid, lang, use_cache=True)
    else:
        data = await remnawave.get_user_stats(uuid)
        if data:
            resp = data.get("response", data)
            text = await _build_stats_text(resp, uuid, lang)
        else:
            text = t(lang, "no_data")

    await call.message.edit_text(
        text,
        reply_markup=stats_navigation_kb(index, len(all_users), uuid),
        parse_mode="HTML",
    )


# ── Account Management ─────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:account")
async def cb_account(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(t(lang, "stats_loading"), reply_markup=back_to_menu_kb(lang))

    all_users = await remnawave.get_all_users_by_telegram_id(call.from_user.id)

    if not all_users:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    accounts = []
    for u in all_users:
        accounts.append(
            {
                "username": u.get("username", "—"),
                "uuid": u.get("uuid"),
                "status": u.get("status", "UNKNOWN"),
            }
        )

    count = len(accounts)
    text = f"👤 <b>{'مدیریت اکانت' if lang == 'fa' else 'Account Management'}</b>\n\n{count} {'اکانت یافت شد' if count == 1 else 'اکانت یافت شدند' if lang == 'fa' else 'accounts found'}:"
    await call.message.edit_text(
        text, reply_markup=account_list_kb(accounts, lang), parse_mode="HTML"
    )


@router.callback_query(F.data == "account:list")
async def cb_account_list(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(t(lang, "stats_loading"), reply_markup=back_to_menu_kb(lang))

    all_users = await remnawave.get_all_users_by_telegram_id(call.from_user.id)

    if not all_users:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    accounts = []
    for u in all_users:
        accounts.append(
            {
                "username": u.get("username", "—"),
                "uuid": u.get("uuid"),
                "status": u.get("status", "UNKNOWN"),
            }
        )

    count = len(accounts)
    text = f"👤 <b>{'مدیریت اکانت' if lang == 'fa' else 'Account Management'}</b>\n\n{count} {'اکانت یافت شد' if count == 1 else 'اکانت یافت شدند' if lang == 'fa' else 'accounts found'}:"
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

    cache = await _get_user_stats_from_cache(session, uuid)

    if cache:
        text = await _build_stats_text(cache, uuid, lang, use_cache=True)
    else:
        data = await remnawave.get_user_stats(uuid)
        if data:
            text = await _build_stats_text(data.get("response", data), uuid, lang)
        else:
            text = t(lang, "no_data")

    await call.message.edit_text(
        text, reply_markup=account_detail_kb(uuid, lang), parse_mode="HTML"
    )


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
    await call.message.edit_text(
        t(lang, "tutorial_os_select"), reply_markup=tutorial_os_select_kb(lang)
    )


@router.callback_query(F.data.startswith("tutorial:os:"))
async def cb_tutorial_os(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    os_type = call.data.split(":")[-1]
    await call.answer()
    await call.message.edit_text(
        t(lang, "tutorial_app_select"), reply_markup=tutorial_app_select_kb(os_type, lang)
    )


@router.callback_query(F.data == "tutorial:back_to_os")
async def cb_tutorial_back_to_os(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await call.message.edit_text(
        t(lang, "tutorial_os_select"), reply_markup=tutorial_os_select_kb(lang)
    )


@router.callback_query(F.data.startswith("tutorial:app:"))
async def cb_tutorial_app(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    _, _, os_type, app = call.data.split(":")

    app_key = f"tutorial_{os_type}_{app}"
    url = getattr(cfg, app_key, "")

    os_names = {"android": "Android", "ios": "iOS", "windows": "Windows"}
    app_names = {"happ": "HAPP", "hiddify": "Hiddify", "v2rayng": "V2rayNG"}

    await call.answer()
    await call.message.edit_text(
        t(lang, "tutorial_view").format(
            os=os_names.get(os_type, os_type), app=app_names.get(app, app)
        ),
        reply_markup=tutorial_view_kb(lang, url) if url else back_to_menu_kb(lang),
    )


@router.callback_query(F.data == "tutorial:back_to_apps")
async def cb_tutorial_back_to_apps(
    call: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    data = await state.get_data()
    os_type = data.get("last_os", "android")
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await call.message.edit_text(
        t(lang, "tutorial_app_select"), reply_markup=tutorial_app_select_kb(os_type, lang)
    )


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


@router.callback_query(F.data == "settings:warnings")
async def cb_settings_warnings(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    await call.message.edit_text(
        t(lang, "settings_warnings_title"),
        reply_markup=settings_warnings_kb(lang),
    )


@router.callback_query(F.data == "settings:warning:expiry")
async def cb_warning_expiry(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    user.expiry_warning_enabled = not getattr(user, "expiry_warning_enabled", True)
    await session.commit()
    await call.message.edit_text(
        t(lang, "settings_warnings_title"),
        reply_markup=settings_warnings_kb(lang, expiry_enabled=user.expiry_warning_enabled),
    )


@router.callback_query(F.data == "settings:warning:volume")
async def cb_warning_volume(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()
    user.volume_warning_enabled = not getattr(user, "volume_warning_enabled", True)
    await session.commit()
    await call.message.edit_text(
        t(lang, "settings_warnings_title"),
        reply_markup=settings_warnings_kb(lang, volume_enabled=user.volume_warning_enabled),
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
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(
        f"🖥️ <b>{'پنل مدیریت' if lang == 'fa' else 'Admin Panel'}</b>\n\n{'لطفاً یک گزینه را انتخاب کنید:' if lang == 'fa' else 'Please select an option:'}",
        reply_markup=admin_main_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:panel")
async def cb_admin_panel(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(
        f"🖥️ <b>{'پنل مدیریت' if lang == 'fa' else 'Admin Panel'}</b>\n\n{'لطفاً یک گزینه را انتخاب کنید:' if lang == 'fa' else 'Please select an option:'}",
        reply_markup=admin_main_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:users")
async def cb_admin_users(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await call.message.edit_text(
        f"👥 <b>{'مدیریت کاربران' if lang == 'fa' else 'User Management'}</b>\n\n{'لطفاً یک گزینه را انتخاب کنید:' if lang == 'fa' else 'Please select an option:'}",
        reply_markup=admin_users_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await call.message.edit_text(
        f"📊 <b>{'گزارش‌ها و آمار' if lang == 'fa' else 'Reports & Statistics'}</b>\n\n{'لطفاً یک گزینه را انتخاب کنید:' if lang == 'fa' else 'Please select an option:'}",
        reply_markup=admin_stats_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:user:add")
async def cb_admin_user_add(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await state.set_state(Admin.waiting_for_telegram_id)
    await call.message.edit_text(
        f"➕ <b>{'افزودن کاربر جدید' if lang == 'fa' else 'Add New User'}</b>\n\n"
        f"{'لطفاً آیدی تلگرام کاربر را وارد کنید:' if lang == 'fa' else 'Please enter the Telegram ID of the user:'}",
        reply_markup=back_to_menu_kb(lang),
        parse_mode="HTML",
    )


@router.message(Admin.waiting_for_telegram_id)
async def handle_admin_telegram_id(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    try:
        telegram_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            f"⚠️ {'لطفاً عدد معتبر وارد کنید.' if lang == 'fa' else 'Please enter a valid number.'}",
            reply_markup=back_to_menu_kb(lang),
        )
        return

    existing = await _get_user(session, telegram_id)
    if existing:
        await message.answer(
            f"⚠️ {'این کاربر قبلاً ثبت شده است.' if lang == 'fa' else 'This user is already registered.'}\n"
            f"Telegram ID: <code>{telegram_id}</code>",
            reply_markup=admin_users_kb(lang),
            parse_mode="HTML",
        )
        await state.clear()
        return

    new_user = User(
        telegram_id=telegram_id,
        username=None,
        full_name=None,
        lang="fa",
        balance=0,
        is_registered=False,
        remnawave_uuid=None,
    )
    session.add(new_user)
    await session.commit()

    await message.answer(
        f"✅ <b>{'کاربر جدید افزوده شد!' if lang == 'fa' else 'New user added!'}</b>\n"
        f"Telegram ID: <code>{telegram_id}</code>",
        reply_markup=admin_users_kb(lang),
        parse_mode="HTML",
    )
    await state.clear()


@router.callback_query(F.data == "admin:user:list")
async def cb_admin_user_list(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await _show_user_list(call, session, lang, page=0)


async def _show_user_list(
    call: CallbackQuery, session: AsyncSession, lang: str, page: int = 0
) -> None:
    page_size = 20
    offset = page * page_size

    result = await session.execute(
        select(User).order_by(User.id.desc()).limit(page_size).offset(offset)
    )
    users = result.scalars().all()

    count_result = await session.execute(select(func.count(User.id)))
    total_count = count_result.scalar() or 0
    total_pages = (total_count + page_size - 1) // page_size

    if not users:
        await call.message.edit_text(
            f"📋 <b>{'لیست کاربران' if lang == 'fa' else 'User List'}</b>\n\n{'کاربری یافت نشد.' if lang == 'fa' else 'No users found.'}",
            reply_markup=admin_users_kb(lang),
            parse_mode="HTML",
        )
        return

    lines = [f"📋 <b>{'لیست کاربران' if lang == 'fa' else 'User List'}</b>\n"]
    lines.append(
        f"{'صفحه' if lang == 'fa' else 'Page'} {page + 1} / {total_pages} | {'تعداد کل' if lang == 'fa' else 'Total'}: {total_count}\n"
    )

    for u in users:
        status = "✅" if u.is_registered else "❌"
        username = f"@{u.username}" if u.username else "—"
        balance_text = f"{u.balance:,}"
        lines.append(f"{status} <code>{u.telegram_id}</code> | {username} | 💰 {balance_text}")

    text = "\n".join(lines)
    await call.message.edit_text(
        text,
        reply_markup=admin_user_list_kb(page, total_pages, lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:user:list:"))
async def cb_admin_user_list_page(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = int(call.data.split(":")[-1])
    await _show_user_list(call, session, lang, page=page)


@router.callback_query(F.data == "admin:user:search")
async def cb_admin_user_search(
    call: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await state.set_state(Admin.waiting_for_search)
    await call.message.edit_text(
        f"🔍 <b>{'جستجوی کاربر' if lang == 'fa' else 'Search User'}</b>\n\n"
        f"{'آیدی تلگرام یا نام کاربری را وارد کنید:' if lang == 'fa' else 'Enter Telegram ID or username:'}",
        reply_markup=back_to_menu_kb(lang),
        parse_mode="HTML",
    )


@router.message(Admin.waiting_for_search)
async def handle_admin_search(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    query = message.text.strip()

    try:
        telegram_id = int(query)
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        found_user = result.scalar_one_or_none()
    except ValueError:
        username = query.replace("@", "")
        result = await session.execute(select(User).where(User.username.ilike(f"%{username}%")))
        found_users = result.scalars().all()
        if len(found_users) == 1:
            found_user = found_users[0]
        elif len(found_users) > 1:
            lines = [f"🔍 <b>{'نتایج جستجو' if lang == 'fa' else 'Search Results'}</b>\n"]
            for u in found_users[:10]:
                username = f"@{u.username}" if u.username else "—"
                lines.append(f"<code>{u.telegram_id}</code> | {username}")
            await message.answer(
                "\n".join(lines),
                reply_markup=admin_users_kb(lang),
                parse_mode="HTML",
            )
            await state.clear()
            return
        else:
            found_user = None

    if found_user:
        balance_text = f"{found_user.balance:,}"
        text = (
            f"👤 <b>{'اطلاعات کاربر' if lang == 'fa' else 'User Info'}</b>\n\n"
            f"🆔 Telegram ID: <code>{found_user.telegram_id}</code>\n"
            f"👤 {'نام کاربری' if lang == 'fa' else 'Username'}: @{found_user.username or '—'}\n"
            f"📛 {'نام' if lang == 'fa' else 'Name'}: {found_user.full_name or '—'}\n"
            f"💰 {'موجودی' if lang == 'fa' else 'Balance'}: {balance_text} {'تومان' if lang == 'fa' else 'Toman'}\n"
            f"📅 {'ثبت‌نام' if lang == 'fa' else 'Registered'}: {'✅' if found_user.is_registered else '❌'}\n"
            f"🌐 {'زبان' if lang == 'fa' else 'Language'}: {found_user.lang}"
        )
    else:
        text = f"⚠️ {'کاربر یافت نشد.' if lang == 'fa' else 'User not found.'}"

    await message.answer(
        text,
        reply_markup=admin_users_kb(lang),
        parse_mode="HTML",
    )
    await state.clear()


@router.callback_query(F.data == "admin:stats:active_24h")
async def cb_admin_stats_active_24h(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await call.message.edit_text(
        f"🟢 <b>{'کاربران آنلاین 24 ساعت اخیر' if lang == 'fa' else 'Online Users (24h)'}</b>\n\n"
        f"{'به زودی...' if lang == 'fa' else 'Coming soon...'}",
        reply_markup=admin_stats_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:stats:inactive_7d")
async def cb_admin_stats_inactive_7d(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await call.message.edit_text(
        f"🟡 <b>{'کاربران غیرفعال 1 تا 7 روز' if lang == 'fa' else 'Inactive Users (1-7 days)'}</b>\n\n"
        f"{'به زودی...' if lang == 'fa' else 'Coming soon...'}",
        reply_markup=admin_stats_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:stats:never")
async def cb_admin_stats_never(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    result = await session.execute(select(User).where(User.is_registered == False))
    users = result.scalars().all()
    total = len(users)

    if total == 0:
        text = f"🔴 <b>{'کاربرانی که هرگز متصل نشده‌اند' if lang == 'fa' else 'Never Connected Users'}</b>\n\n{'کاربری یافت نشد.' if lang == 'fa' else 'No users found.'}"
    else:
        lines = [
            f"🔴 <b>{'کاربرانی که هرگز متصل نشده‌اند' if lang == 'fa' else 'Never Connected Users'}</b>\n"
        ]
        lines.append(f"{'تعداد' if lang == 'fa' else 'Total'}: {total}\n")
        for u in users[:20]:
            username = f"@{u.username}" if u.username else "—"
            lines.append(f"<code>{u.telegram_id}</code> | {username}")
        if total > 20:
            lines.append(
                f"... {'و' if lang == 'fa' else 'and'} {total - 20} {'نفر دیگر' if lang == 'fa' else 'more'}"
            )
        text = "\n".join(lines)

    await call.message.edit_text(
        text,
        reply_markup=admin_stats_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:stats:all_users")
async def cb_admin_stats_all_users(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    result = await session.execute(select(func.count(User.id)))
    total = result.scalar() or 0

    result = await session.execute(select(func.count(User.id)).where(User.is_registered == True))
    registered = result.scalar() or 0

    result = await session.execute(select(func.count(User.id)).where(User.is_registered == False))
    not_registered = result.scalar() or 0

    text = (
        f"👥 <b>{'لیست کاربران ربات' if lang == 'fa' else 'Bot Users List'}</b>\n\n"
        f"📊 {'آمار کلی:' if lang == 'fa' else 'Total Statistics:'}:\n"
        f"• {'کل کاربران' if lang == 'fa' else 'Total Users'}: {total}\n"
        f"• {'ثبت‌نام شده' if lang == 'fa' else 'Registered'}: {registered}\n"
        f"• {'ثبت‌نام نشده' if lang == 'fa' else 'Not Registered'}: {not_registered}"
    )

    await call.message.edit_text(
        text,
        reply_markup=admin_stats_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:stats:balances")
async def cb_admin_stats_balances(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    result = await session.execute(select(func.sum(User.balance)))
    total_balance = result.scalar() or 0

    result = await session.execute(
        select(User).where(User.balance > 0).order_by(User.balance.desc()).limit(50)
    )
    users_with_balance = result.scalars().all()

    lines = [f"💰 <b>{'موجودی کاربران' if lang == 'fa' else 'User Balances'}</b>\n"]
    lines.append(
        f"{'کل موجودی' if lang == 'fa' else 'Total Balance'}: {total_balance:,} {'تومان' if lang == 'fa' else 'Toman'}\n"
    )

    if users_with_balance:
        lines.append(f"\n{'کاربران با موجودی:' if lang == 'fa' else 'Users with balance:'}")

        result = await session.execute(select(func.count(User.id)).where(User.balance > 0))
        count_with_balance = result.scalar() or 0
        lines.append(f"{'تعداد' if lang == 'fa' else 'Count'}: {count_with_balance}\n")

        for u in users_with_balance[:20]:
            username = f"@{u.username}" if u.username else "—"
            balance_text = f"{u.balance:,}"
            lines.append(f"<code>{u.telegram_id}</code> | {username} | 💰 {balance_text}")

        if count_with_balance > 20:
            lines.append(
                f"... {'و' if lang == 'fa' else 'and'} {count_with_balance - 20} {'نفر دیگر' if lang == 'fa' else 'more'}"
            )

    text = "\n".join(lines)
    await call.message.edit_text(
        text,
        reply_markup=admin_stats_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:backup")
async def cb_admin_backup(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await call.message.edit_text(
        f"💾 <b>{'پشتیبان‌گیری' if lang == 'fa' else 'Backup'}</b>\n\n"
        f"{'به زودی...' if lang == 'fa' else 'Coming soon...'}",
        reply_markup=admin_main_kb(lang),
        parse_mode="HTML",
    )
