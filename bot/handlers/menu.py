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
    admin_packages_kb,
    package_list_kb,
    package_edit_kb,
    user_packages_kb,
    user_packages_category_kb,
)
from bot.config import settings as cfg
from bot.remnawave.client import remnawave
from bot.utils.date import to_persian_date, days_until_persian
from bot.states.fsm import Admin, Package

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

    if not user:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(
        f"🚀 <b>{'پلن‌های فروش سرویس' if lang == 'fa' else 'Service Plans'}</b>\n\n"
        f"{'💡 لطفاً دسته‌بندی مورد نظر را انتخاب کنید:' if lang == 'fa' else '💡 Please select a category:'}",
        reply_markup=user_packages_category_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("packages:category:"))
async def cb_packages_category(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    category = call.data.split(":")[-1]

    from bot.db.models import Package as PackageModel

    result = await session.execute(
        select(PackageModel)
        .where(PackageModel.is_active == True)
        .where(PackageModel.category == category)
        .order_by(PackageModel.sort_order, PackageModel.price)
    )
    packages = result.scalars().all()

    if not packages:
        await call.message.edit_text(
            f"📦 <b>{'در این دسته‌بندی بسته‌ای موجود نیست.' if lang == 'fa' else 'No packages available in this category.'}</b>",
            reply_markup=user_packages_category_kb(lang),
            parse_mode="HTML",
        )
        return

    text, keyboard = user_packages_kb(packages, lang, user.balance, category)
    await call.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "packages:back")
async def cb_packages_back(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    await call.message.edit_text(
        f"🚀 <b>{'پلن‌های فروش سرویس' if lang == 'fa' else 'Service Plans'}</b>\n\n"
        f"{'💡 لطفاً دسته‌بندی مورد نظر را انتخاب کنید:' if lang == 'fa' else '💡 Please select a category:'}",
        reply_markup=user_packages_category_kb(lang),
        parse_mode="HTML",
    )


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


@router.callback_query(F.data == "admin:packages")
async def cb_admin_packages(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await call.message.edit_text(
        f"📦 <b>{'مدیریت بسته‌ها' if lang == 'fa' else 'Package Management'}</b>\n\n{'لطفاً یک گزینه را انتخاب کنید:' if lang == 'fa' else 'Please select an option:'}",
        reply_markup=admin_packages_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:package:add")
async def cb_admin_package_add(
    call: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await state.set_state(Package.waiting_for_name)
    await state.update_data(package_message_id=call.message.message_id)
    await call.message.edit_text(
        f"➕ <b>{'افزودن بسته جدید' if lang == 'fa' else 'Add New Package'}</b>\n\n"
        f"{'لطفاً نام بسته را وارد کنید:' if lang == 'fa' else 'Please enter the package name:'}",
        reply_markup=back_to_menu_kb(lang),
        parse_mode="HTML",
    )


@router.message(Package.waiting_for_name)
async def handle_package_name(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    data = await state.get_data()
    message_id = data.get("package_message_id")

    await state.update_data(name=message.text.strip())
    await state.set_state(Package.waiting_for_volume)

    text = (
        f"📦 <b>{'حجم بسته' if lang == 'fa' else 'Package Volume'}</b>\n\n"
        f"{'لطفاً حجم بسته را به گیگابایت وارد کنید:' if lang == 'fa' else 'Please enter the package volume in GB:'}"
    )
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message_id,
            text=text,
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(text, reply_markup=back_to_menu_kb(lang), parse_mode="HTML")


@router.message(Package.waiting_for_volume)
async def handle_package_volume(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    data = await state.get_data()
    message_id = data.get("package_message_id")

    try:
        volume = int(message.text.strip())
        if volume <= 0:
            raise ValueError()
    except ValueError:
        await message.answer(
            f"❌ {'لطفاً عدد معتبر وارد کنید:' if lang == 'fa' else 'Please enter a valid number:'}",
        )
        return

    await state.update_data(volume_gb=volume)
    await state.set_state(Package.waiting_for_days)

    text = (
        f"📅 <b>{'مدت بسته' if lang == 'fa' else 'Package Duration'}</b>\n\n"
        f"{'لطفاً تعداد روز را وارد کنید:' if lang == 'fa' else 'Please enter the number of days:'}"
    )
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message_id,
            text=text,
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(text, reply_markup=back_to_menu_kb(lang), parse_mode="HTML")


@router.message(Package.waiting_for_days)
async def handle_package_days(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    data = await state.get_data()
    message_id = data.get("package_message_id")

    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError()
    except ValueError:
        await message.answer(
            f"❌ {'لطفاً عدد معتبر وارد کنید:' if lang == 'fa' else 'Please enter a valid number:'}",
        )
        return

    await state.update_data(days=days)
    await state.set_state(Package.waiting_for_price)

    text = (
        f"💰 <b>{'قیمت بسته' if lang == 'fa' else 'Package Price'}</b>\n\n"
        f"{'لطفاً قیمت را به تومان وارد کنید:' if lang == 'fa' else 'Please enter the price in Toman:'}"
    )
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message_id,
            text=text,
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(text, reply_markup=back_to_menu_kb(lang), parse_mode="HTML")


@router.message(Package.waiting_for_price)
async def handle_package_price(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    data = await state.get_data()
    message_id = data.get("package_message_id")

    try:
        price = int(message.text.strip().replace(",", ""))
        if price <= 0:
            raise ValueError()
    except ValueError:
        await message.answer(
            f"❌ {'لطفاً عدد معتبر وارد کنید:' if lang == 'fa' else 'Please enter a valid number:'}",
        )
        return

    await state.update_data(price=price)
    await state.set_state(Package.waiting_for_category)

    text = (
        f"📂 <b>{'دسته‌بندی' if lang == 'fa' else 'Category'}</b>\n\n"
        f"{'لطفاً دسته‌بندی بسته را انتخاب کنید:' if lang == 'fa' else 'Please select the package category:'}\n\n"
        f"1 - 💰 {'اقتصادی' if lang == 'fa' else 'Economy'}\n"
        f"2 - 👑 {'ویژه (VIP)' if lang == 'fa' else 'VIP'}\n"
        f"3 - 🌐 {'تانل' if lang == 'fa' else 'Tunnel'}"
    )
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message_id,
            text=text,
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(text, reply_markup=back_to_menu_kb(lang), parse_mode="HTML")


@router.message(Package.waiting_for_category)
async def handle_package_category(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    data = await state.get_data()
    message_id = data.get("package_message_id")

    category_map = {
        "1": "economy",
        "2": "vip",
        "3": "tunnel",
        "economy": "economy",
        "vip": "vip",
        "tunnel": "tunnel",
        "اقتصادی": "economy",
        "ویژه": "vip",
        "تانل": "tunnel",
    }

    category_input = message.text.strip().lower()
    category = category_map.get(category_input)

    if not category:
        await message.answer(
            f"❌ {'لطفاً عدد معتبر انتخاب کنید:' if lang == 'fa' else 'Please select a valid number:'}\n\n"
            f"1 - 💰 {'اقتصادی' if lang == 'fa' else 'Economy'}\n"
            f"2 - 👑 {'ویژه (VIP)' if lang == 'fa' else 'VIP'}\n"
            f"3 - 🌐 {'تانل' if lang == 'fa' else 'Tunnel'}",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()

    from bot.db.models import Package as PackageModel

    pkg = PackageModel(
        name=data["name"],
        volume_gb=data["volume_gb"],
        days=data["days"],
        price=data["price"],
        category=category,
    )
    session.add(pkg)
    await session.commit()

    category_names = {"economy": "💰 اقتصادی", "vip": "👑 ویژه", "tunnel": "🌐 تانل"}
    cat_name = category_names.get(category, category)

    await state.clear()

    text = (
        f"✅ <b>{'بسته ایجاد شد!' if lang == 'fa' else 'Package created!'}</b>\n\n"
        f"<b>{'نام:' if lang == 'fa' else 'Name:'}</b> {pkg.name}\n"
        f"<b>{'حجم:' if lang == 'fa' else 'Volume:'}</b> {pkg.volume_gb} GB\n"
        f"<b>{'مدت:' if lang == 'fa' else 'Duration:'}</b> {pkg.days} {'روز' if lang == 'fa' else 'days'}\n"
        f"<b>{'قیمت:' if lang == 'fa' else 'Price:'}</b> {pkg.price:,} {'تومان' if lang == 'fa' else 'IRR'}\n"
        f"<b>{'دسته:' if lang == 'fa' else 'Category:'}</b> {cat_name}"
    )
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message_id,
            text=text,
            reply_markup=admin_packages_kb(lang),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(text, reply_markup=admin_packages_kb(lang), parse_mode="HTML")


@router.callback_query(F.data == "admin:package:list")
async def cb_admin_package_list(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    from bot.db.models import Package as PackageModel

    result = await session.execute(
        select(PackageModel).order_by(PackageModel.sort_order, PackageModel.id)
    )
    packages = result.scalars().all()

    if not packages:
        await call.message.edit_text(
            f"📦 <b>{'بسته‌ها' if lang == 'fa' else 'Packages'}</b>\n\n"
            f"{'بسته‌ای یافت نشد.' if lang == 'fa' else 'No packages found.'}",
            reply_markup=admin_packages_kb(lang),
            parse_mode="HTML",
        )
        return

    await call.message.edit_text(
        f"📦 <b>{'بسته‌های موجود' if lang == 'fa' else 'Available Packages'}</b>\n\n"
        f"{'برای مدیریت روی هر بسته کلیک کنید:' if lang == 'fa' else 'Click on a package to manage:'}",
        reply_markup=package_list_kb(packages, lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("package:edit:"))
async def cb_package_edit(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    pkg_id = int(call.data.split(":")[-1])
    from bot.db.models import Package as PackageModel

    result = await session.execute(select(PackageModel).where(PackageModel.id == pkg_id))
    pkg = result.scalar_one_or_none()

    if not pkg:
        return

    await call.message.edit_text(
        f"📦 <b>{pkg.name}</b>\n\n"
        f"<b>{'حجم:' if lang == 'fa' else 'Volume:'}</b> {pkg.volume_gb} GB\n"
        f"<b>{'مدت:' if lang == 'fa' else 'Duration:'}</b> {pkg.days} {'روز' if lang == 'fa' else 'days'}\n"
        f"<b>{'کشور:' if lang == 'fa' else 'Country:'}</b> {pkg.country or '-'}\n"
        f"<b>{'وضعیت:' if lang == 'fa' else 'Status:'}</b> {'✅ فعال' if pkg.is_active else '❌ غیرفعال'}",
        reply_markup=package_edit_kb(pkg.id, lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("package:toggle:"))
async def cb_package_toggle(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    _, _, pkg_id, status = call.data.split(":")
    pkg_id = int(pkg_id)
    is_active = status == "1"

    from bot.db.models import Package as PackageModel

    result = await session.execute(select(PackageModel).where(PackageModel.id == pkg_id))
    pkg = result.scalar_one_or_none()

    if not pkg:
        return

    pkg.is_active = is_active
    await session.commit()

    await call.message.edit_text(
        f"📦 <b>{pkg.name}</b>\n\n"
        f"<b>{'حجم:' if lang == 'fa' else 'Volume:'}</b> {pkg.volume_gb} GB\n"
        f"<b>{'مدت:' if lang == 'fa' else 'Duration:'}</b> {pkg.days} {'روز' if lang == 'fa' else 'days'}\n"
        f"<b>{'کشور:' if lang == 'fa' else 'Country:'}</b> {pkg.country or '-'}\n"
        f"<b>{'وضعیت:' if lang == 'fa' else 'Status:'}</b> {'✅ فعال' if pkg.is_active else '❌ غیرفعال'}",
        reply_markup=package_edit_kb(pkg.id, lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("package:delete:"))
async def cb_package_delete(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    pkg_id = int(call.data.split(":")[-1])

    from bot.db.models import Package as PackageModel

    result = await session.execute(select(PackageModel).where(PackageModel.id == pkg_id))
    pkg = result.scalar_one_or_none()

    if not pkg:
        return

    await session.delete(pkg)
    await session.commit()

    await call.message.edit_text(
        f"✅ <b>{'بسته حذف شد!' if lang == 'fa' else 'Package deleted!'}",
        reply_markup=admin_packages_kb(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("package:buy:"))
async def cb_package_buy(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    pkg_id = int(call.data.split(":")[-1])

    from bot.db.models import Package as PackageModel

    result = await session.execute(select(PackageModel).where(PackageModel.id == pkg_id))
    pkg = result.scalar_one_or_none()

    if not pkg or not pkg.is_active:
        await call.message.edit_text(
            f"❌ {'این بسته فعال نیست.' if lang == 'fa' else 'This package is not active.'}",
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
        return

    price_text = f"{pkg.price:,}"
    await call.message.edit_text(
        f"🛒 <b>{'خرید بسته' if lang == 'fa' else 'Purchase Package'}</b>\n\n"
        f"<b>{'بسته:' if lang == 'fa' else 'Package:'}</b> {pkg.name}\n"
        f"<b>{'حجم:' if lang == 'fa' else 'Volume:'}</b> {pkg.volume_gb} GB\n"
        f"<b>{'مدت:' if lang == 'fa' else 'Duration:'}</b> {pkg.days} {'روز' if lang == 'fa' else 'days'}\n"
        f"<b>{'قیمت:' if lang == 'fa' else 'Price:'}</b> {price_text} {'تومان' if lang == 'fa' else 'IRR'}\n\n"
        f"{'برای ادامه خرید با پشتیبانی تماس بگیرید.' if lang == 'fa' else 'Contact support to complete your purchase.'}\n\n"
        f"<b>ID:</b> <code>{pkg.id}</code>",
        reply_markup=back_to_menu_kb(lang),
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
