from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
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
    admin_stats_back_kb,
    admin_user_list_kb,
    admin_bot_user_list_kb,
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
from bot.remnawave.client import (
    remnawave,
    get_internal_squads,
    create_remnawave_user,
    revoke_user_subscription,
    reset_and_set_user_package,
)
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


def _format_bytes(bytes_val: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"


@router.callback_query(F.data == "menu:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if not user:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    all_users = await remnawave.get_all_users_by_telegram_id(call.from_user.id)

    if not all_users or not all_users[-1].get("uuid"):
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    uuid = all_users[-1].get("uuid")
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

    all_users = await remnawave.get_all_users_by_telegram_id(call.from_user.id)

    if not all_users:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    accounts = []
    for u in all_users:
        username = u.get("username", "—")

        used_bytes = u.get("userTraffic", {}).get("usedTrafficBytes", 0) or 0
        total_bytes = u.get("trafficLimitBytes", 0) or 0
        expire_at = u.get("expireAt")

        usage_percent = 0
        days_remaining = 0

        if total_bytes and total_bytes > 0:
            usage_percent = int((used_bytes / total_bytes) * 100)

        if expire_at:
            try:
                from datetime import datetime, timezone

                exp = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
                days_remaining = max(0, (exp - datetime.now(timezone.utc)).days)
            except:
                days_remaining = 0

        accounts.append(
            {
                "username": username,
                "uuid": u.get("uuid"),
                "usage_percent": usage_percent,
                "days_remaining": days_remaining,
            }
        )

    text = f"👤 <b>{'مدیریت اکانت' if lang == 'fa' else 'Account Management'}</b>"
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

    all_users = await remnawave.get_all_users_by_telegram_id(call.from_user.id)

    if not all_users:
        await call.message.edit_text(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    accounts = []
    for u in all_users:
        username = u.get("username", "—")

        used_bytes = u.get("userTraffic", {}).get("usedTrafficBytes", 0) or 0
        total_bytes = u.get("trafficLimitBytes", 0) or 0
        expire_at = u.get("expireAt")

        usage_percent = 0
        days_remaining = 0

        if total_bytes and total_bytes > 0:
            usage_percent = int((used_bytes / total_bytes) * 100)

        if expire_at:
            try:
                from datetime import datetime, timezone

                exp = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
                days_remaining = max(0, (exp - datetime.now(timezone.utc)).days)
            except:
                days_remaining = 0

        accounts.append(
            {
                "username": username,
                "uuid": u.get("uuid"),
                "usage_percent": usage_percent,
                "days_remaining": days_remaining,
            }
        )

    text = f"👤 <b>{'مدیریت اکانت' if lang == 'fa' else 'Account Management'}</b>"
    await call.message.edit_text(
        text, reply_markup=account_list_kb(accounts, lang), parse_mode="HTML"
    )


@router.callback_query(F.data == "#")
async def cbnoop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data.startswith("account:"))
async def cb_account_detail(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    data_parts = call.data.split(":")
    action = data_parts[1] if len(data_parts) > 1 else ""

    if action == "link":
        import qrcode
        import tempfile
        import os
        from aiogram.types import FSInputFile

        uuid = data_parts[2] if len(data_parts) > 2 else ""
        if not uuid:
            await call.message.edit_text(t(lang, "error"), reply_markup=back_to_menu_kb(lang))
            return

        data = await remnawave.get_user_stats(uuid)
        if data:
            resp = data.get("response", data)
            sub_url = resp.get("subscriptionUrl", "")
            short_uuid = resp.get("shortUuid", "")
            username = resp.get("username", "")

            if sub_url:
                short_link = f"https://docs.cloudvibe.ir/{short_uuid}" if short_uuid else sub_url

                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(short_link)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")

                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                img.save(temp_file.name, format="PNG")
                temp_file.close()

                text = (
                    f"🔗 <b>{'لینک اشتراک شما (Normal) آماده است' if lang == 'fa' else 'Your subscription link (Normal) is ready'}</b>\n\n"
                    f"{'۱. برای کپی کردن، روی لینک زیر ضربه بزنید:' if lang == 'fa' else '1. Tap the link below to copy:'}\n"
                    f"<code>{sub_url}</code>"
                )

                kb = [
                    [
                        InlineKeyboardButton(
                            text="🔄 عوض کردن لینک", callback_data=f"account:revoke:{uuid}"
                        )
                    ],
                    [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"account:{uuid}")],
                ]

                try:
                    await call.message.answer_photo(
                        photo=FSInputFile(temp_file.name),
                        caption=text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                        parse_mode="HTML",
                    )
                    try:
                        await call.message.delete()
                    except:
                        pass
                except Exception:
                    pass
                os.unlink(temp_file.name)
            else:
                try:
                    await call.message.edit_text(
                        f"❌ {'لینک یافت نشد' if lang == 'fa' else 'Link not found'}",
                        reply_markup=account_detail_kb(uuid, lang),
                        parse_mode="HTML",
                    )
                except:
                    pass
        else:
            await call.message.edit_text(
                t(lang, "error"),
                reply_markup=account_detail_kb(uuid, lang),
            )
        return

    if action == "revoke":
        import qrcode
        import tempfile
        import os
        from aiogram.types import FSInputFile

        uuid = data_parts[2] if len(data_parts) > 2 else ""
        if not uuid:
            try:
                await call.message.edit_text(t(lang, "error"), reply_markup=back_to_menu_kb(lang))
            except Exception:
                await call.message.answer(t(lang, "error"), reply_markup=back_to_menu_kb(lang))
            return

        loading_msg = None

        revoke_result = await revoke_user_subscription(uuid)
        if not revoke_result:
            if loading_msg:
                try:
                    await loading_msg.delete()
                except:
                    pass
            try:
                await call.message.edit_text(
                    f"❌ {'خطا در عوض کردن لینک' if lang == 'fa' else 'Error revoking link'}",
                    reply_markup=account_detail_kb(uuid, lang),
                    parse_mode="HTML",
                )
            except Exception:
                await call.message.answer(
                    f"❌ {'خطا در عوض کردن لینک' if lang == 'fa' else 'Error revoking link'}",
                    reply_markup=account_detail_kb(uuid, lang),
                    parse_mode="HTML",
                )
            return

        data = await remnawave.get_user_stats(uuid)
        if data:
            resp = data.get("response", data)
            sub_url = resp.get("subscriptionUrl", "")
            short_uuid = resp.get("shortUuid", "")

            if sub_url:
                short_link = f"https://docs.cloudvibe.ir/{short_uuid}" if short_uuid else sub_url

                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(short_link)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")

                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                img.save(temp_file.name, format="PNG")
                temp_file.close()

                text = (
                    f"🔗 <b>{'لینک اشتراک شما (Normal) آماده است' if lang == 'fa' else 'Your subscription link (Normal) is ready'}</b>\n\n"
                    f"{'۱. برای کپی کردن، روی لینک زیر ضربه بزنید:' if lang == 'fa' else '1. Tap the link below to copy:'}\n"
                    f"<code>{sub_url}</code>"
                )

                kb = [
                    [
                        InlineKeyboardButton(
                            text="🔄 عوض کردن لینک", callback_data=f"account:revoke:{uuid}"
                        )
                    ],
                    [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"account:{uuid}")],
                ]

                try:
                    await call.message.answer_photo(
                        photo=FSInputFile(temp_file.name),
                        caption=text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                        parse_mode="HTML",
                    )
                    if loading_msg:
                        try:
                            await loading_msg.delete()
                        except:
                            pass
                    try:
                        await call.message.delete()
                    except:
                        pass
                except Exception:
                    pass
                os.unlink(temp_file.name)
            else:
                try:
                    await call.message.edit_text(
                        f"❌ {'لینک یافت نشد' if lang == 'fa' else 'Link not found'}",
                        reply_markup=account_detail_kb(uuid, lang),
                        parse_mode="HTML",
                    )
                except Exception:
                    await call.message.answer(
                        f"❌ {'لینک یافت نشد' if lang == 'fa' else 'Link not found'}",
                        reply_markup=account_detail_kb(uuid, lang),
                        parse_mode="HTML",
                    )
        else:
            try:
                await call.message.edit_text(
                    t(lang, "error"),
                    reply_markup=account_detail_kb(uuid, lang),
                )
            except Exception:
                await call.message.answer(
                    t(lang, "error"),
                    reply_markup=account_detail_kb(uuid, lang),
                )
        return
    elif action == "payment":
        uuid = data_parts[2] if len(data_parts) > 2 else ""
        try:
            await call.message.edit_text(
                f"💳 <b>{'سابقه پرداخت' if lang == 'fa' else 'Payment History'}</b>\n\n{'به زودی...' if lang == 'fa' else 'Coming soon...'}",
                reply_markup=account_detail_kb(uuid, lang),
                parse_mode="HTML",
            )
        except Exception:
            await call.message.answer(
                f"💳 <b>{'سابقه پرداخت' if lang == 'fa' else 'Payment History'}</b>\n\n{'به زودی...' if lang == 'fa' else 'Coming soon...'}",
                reply_markup=account_detail_kb(uuid, lang),
                parse_mode="HTML",
            )
        return

    uuid = data_parts[1] if len(data_parts) > 1 else ""
    if not uuid:
        uuid = user.remnawave_uuid if user else ""

    if not uuid:
        try:
            await call.message.edit_text(
                t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang)
            )
        except Exception:
            await call.message.answer(t(lang, "not_authorized"), reply_markup=back_to_menu_kb(lang))
        return

    loading_msg = None

    cache = await _get_user_stats_from_cache(session, uuid)
    days_remaining = None
    volume_remaining_str = None

    if cache:
        text = await _build_stats_text(cache, uuid, lang, use_cache=True)
        if hasattr(cache, "remaining_traffic_bytes"):
            remaining = cache.remaining_traffic_bytes or 0
            if remaining > 0:
                volume_remaining_str = _format_bytes(remaining)
            if cache.expire_at:
                from datetime import datetime, timezone

                exp = cache.expire_at
                if isinstance(exp, str):
                    try:
                        exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                    except:
                        exp = None
                if exp and exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp:
                    days_remaining = (exp - datetime.now(timezone.utc)).days
    else:
        data = await remnawave.get_user_stats(uuid)
        if data:
            resp = data.get("response", data)
            text = await _build_stats_text(resp, uuid, lang)
            remaining = resp.get("remainingTrafficBytes") or resp.get("userTraffic", {}).get(
                "remainingTrafficBytes", 0
            )
            if remaining and remaining > 0:
                volume_remaining_str = _format_bytes(remaining)
            expire_at = resp.get("expireAt")
            if expire_at:
                from datetime import datetime, timezone

                try:
                    exp = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
                    days_remaining = (exp - datetime.now(timezone.utc)).days
                except:
                    pass
        else:
            text = t(lang, "no_data")

    try:
        try:
            await call.message.delete()
        except:
            pass
        await call.message.answer(
            text,
            reply_markup=account_detail_kb(uuid, lang, days_remaining, volume_remaining_str),
            parse_mode="HTML",
        )
    except Exception:
        try:
            await call.message.delete()
        except:
            pass
        await call.message.answer(
            text,
            reply_markup=account_detail_kb(uuid, lang, days_remaining, volume_remaining_str),
            parse_mode="HTML",
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
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="packages:back")]
                ]
            ),
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
@router.callback_query(F.data == "settings:change_lang:from_settings")
async def cb_change_lang(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.update_data(lang_change_from="settings")
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

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        pass

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

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        pass

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

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        pass

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

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        pass

    text = (
        f"📂 <b>{'دسته‌بندی' if lang == 'fa' else 'Category'}</b>\n\n"
        f"{'لطفاً دسته‌بندی بسته را انتخاب کنید:' if lang == 'fa' else 'Please select the package category:'}\n\n"
        f"1 - 💰 {'اقتصادی' if lang == 'fa' else 'Economy'}\n"
        f"2 - 👑 {'ویژه (VIP)' if lang == 'fa' else 'VIP'}\n"
        f"3 - 👑 {'ویژه پلاس (VIP+)' if lang == 'fa' else 'VIP+'}\n"
        f"4 - 🌐 {'تانل' if lang == 'fa' else 'Tunnel'}"
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
        "3": "vip_plus",
        "4": "tunnel",
        "economy": "economy",
        "vip": "vip",
        "vip_plus": "vip_plus",
        "tunnel": "tunnel",
        "اقتصادی": "economy",
        "ویژه": "vip",
        "ویژه پلاس": "vip_plus",
        "vip+": "vip_plus",
        "تانل": "tunnel",
    }

    category_input = message.text.strip().lower()
    category = category_map.get(category_input)

    if not category:
        await message.answer(
            f"❌ {'لطفاً عدد معتبر انتخاب کنید:' if lang == 'fa' else 'Please select a valid number:'}\n\n"
            f"1 - 💰 {'اقتصادی' if lang == 'fa' else 'Economy'}\n"
            f"2 - 👑 {'ویژه (VIP)' if lang == 'fa' else 'VIP'}\n"
            f"3 - 👑 {'ویژه پلاس (VIP+)' if lang == 'fa' else 'VIP+'}\n"
            f"4 - 🌐 {'تانل' if lang == 'fa' else 'Tunnel'}",
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

    category_names = {
        "economy": "💰 اقتصادی",
        "vip": "👑 ویژه",
        "vip_plus": "👑 ویژه پلاس",
        "tunnel": "🌐 تانل",
    }
    cat_name = category_names.get(category, category)

    await state.clear()

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        await bot.delete_message(chat_id=message.chat.id, message_id=message_id)
    except Exception:
        pass

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
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:packages")]
                ]
            ),
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
        f"<b>{'دسته‌بندی:' if lang == 'fa' else 'Category:'}</b> {pkg.category or '-'}\n"
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

    all_accounts = await remnawave.get_all_users_by_telegram_id(call.from_user.id)

    if not all_accounts:
        await call.message.edit_text(
            f"❌ {'شما هیچ اکانتی ندارید.' if lang == 'fa' else 'You have no accounts.'}",
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
        return

    if len(all_accounts) == 1:
        await process_package_purchase(call, session, user, pkg, all_accounts[0], lang)
    else:
        await show_account_selection_for_purchase(call, user, pkg, all_accounts, lang)


async def show_account_selection_for_purchase(
    call: CallbackQuery, user, pkg, accounts: list, lang: str
) -> None:
    kb_buttons = []
    for acc in accounts:
        username = acc.get("username", "—")
        uuid = acc.get("uuid")
        kb_buttons.append(
            [
                InlineKeyboardButton(
                    text=f"👤 {username}", callback_data=f"package:select:{pkg.id}:{uuid}"
                )
            ]
        )
    kb_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="packages:back")])

    await call.message.edit_text(
        f"🛒 <b>{'انتخاب اکانت' if lang == 'fa' else 'Select Account'}</b>\n\n"
        f"{'لطفاً اکانتی که می‌خواهید بسته را روی آن فعال کنید، انتخاب کنید:' if lang == 'fa' else 'Please select the account you want to activate the package on:'}\n\n"
        f"<b>{'بسته:' if lang == 'fa' else 'Package:'}</b> {pkg.name} ({pkg.volume_gb} GB / {pkg.days} {'روز' if lang == 'fa' else 'days'})\n"
        f"<b>{'قیمت:' if lang == 'fa' else 'Price:'}</b> {pkg.price:,} {'تومان' if lang == 'fa' else 'Toman'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("package:select:"))
async def cb_package_select_account(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    parts = call.data.split(":")
    pkg_id = int(parts[2])
    uuid = parts[3]

    from bot.db.models import Package as PackageModel

    result = await session.execute(select(PackageModel).where(PackageModel.id == pkg_id))
    pkg = result.scalar_one_or_none()

    if not pkg:
        await call.message.edit_text(
            f"❌ {'بسته یافت نشد.' if lang == 'fa' else 'Package not found.'}",
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
        return

    all_accounts = await remnawave.get_all_users_by_telegram_id(call.from_user.id)
    selected_account = next((acc for acc in all_accounts if acc.get("uuid") == uuid), None)

    if not selected_account:
        await call.message.edit_text(
            f"❌ {'اکانت یافت نشد.' if lang == 'fa' else 'Account not found.'}",
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
        return

    await process_package_purchase(call, session, user, pkg, selected_account, lang)


async def process_package_purchase(
    call: CallbackQuery, session: AsyncSession, user, pkg, account: dict, lang: str
) -> None:
    from bot.db.models import Package as PackageModel
    from bot.keyboards.inline import main_menu_kb

    uuid = account.get("uuid")
    username = account.get("username", "—")

    current_used = account.get("userTraffic", {}).get("usedTrafficBytes", 0) or 0
    current_total = account.get("trafficLimitBytes", 0) or 0
    current_expire = account.get("expireAt")

    current_gb = round((current_total - current_used) / (1024**3), 2) if current_total > 0 else 0
    days_left = 0
    if current_expire:
        try:
            exp = datetime.fromisoformat(current_expire.replace("Z", "+00:00"))
            days_left = max(0, (exp - datetime.now(timezone.utc)).days)
        except:
            days_left = 0

    price_text = f"{pkg.price:,}"

    if user.balance < pkg.price:
        await call.message.edit_text(
            f"❌ <b>{'موجودی ناکافی' if lang == 'fa' else 'Insufficient Balance'}</b>\n\n"
            f"{'بسته:' if lang == 'fa' else 'Package:'} {pkg.name}\n"
            f"{'قیمت:' if lang == 'fa' else 'Price:'} {price_text} {'تومان' if lang == 'fa' else 'Toman'}\n"
            f"{'موجودی:' if lang == 'fa' else 'Balance:'} {user.balance:,} {'تومان' if lang == 'fa' else 'Toman'}\n\n"
            f"{'لطفاً کیف پول خود را شارژ کنید.' if lang == 'fa' else 'Please charge your wallet.'}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💰 کیف پول", callback_data="menu:wallet")]
                ]
            ),
            parse_mode="HTML",
        )
        return

    kb_confirm = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تایید و خرید", callback_data=f"package:confirm:{pkg.id}:{uuid}"
                ),
                InlineKeyboardButton(text="❌ لغو", callback_data="packages:back"),
            ]
        ]
    )

    await call.message.edit_text(
        f"🛒 <b>{'خرید بسته' if lang == 'fa' else 'Purchase Package'}</b>\n\n"
        f"<b>{'اکانت:' if lang == 'fa' else 'Account:'} {username}</b>\n"
        f"<b>{'بسته:' if lang == 'fa' else 'Package:'} {pkg.name}</b>\n"
        f"<b>{'حجم:' if lang == 'fa' else 'Volume:'} {pkg.volume_gb} GB</b>\n"
        f"<b>{'مدت:' if lang == 'fa' else 'Duration:'} {pkg.days} {'روز' if lang == 'fa' else 'days'}</b>\n"
        f"<b>{'قیمت:' if lang == 'fa' else 'Price:'} {price_text} {'تومان' if lang == 'fa' else 'Toman'}</b>\n\n"
        f"<b>{'وضعیت فعلی:' if lang == 'fa' else 'Current Status:'}</b>\n"
        f"💾 {'حجم:' if lang == 'fa' else 'Volume:'} {current_gb} GB\n"
        f"📅 {'زمان:' if lang == 'fa' else 'Time:'} {days_left} {'روز' if lang == 'fa' else 'days'}\n\n"
        f"<b>{'هشدار: با خرید این بسته، حجم و زمان فعلی شما ریست می‌شود!' if lang == 'fa' else 'Warning: Your current volume and time will be reset!'}</b>",
        reply_markup=kb_confirm,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("package:confirm:"))
async def cb_package_confirm(call: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    parts = call.data.split(":")
    pkg_id = int(parts[2])
    uuid = parts[3]

    from bot.db.models import Package as PackageModel

    result = await session.execute(select(PackageModel).where(PackageModel.id == pkg_id))
    pkg = result.scalar_one_or_none()

    if not pkg or not pkg.is_active:
        await call.message.edit_text(
            f"❌ {'بسته یافت نشد.' if lang == 'fa' else 'Package not found.'}",
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
        return

    if user.balance < pkg.price:
        await call.message.edit_text(
            f"❌ {'موجودی ناکافی.' if lang == 'fa' else 'Insufficient balance.'}",
            reply_markup=back_to_menu_kb(lang),
            parse_mode="HTML",
        )
        return

    user.balance -= pkg.price
    await session.commit()

    account_data = await remnawave.get_user_stats(uuid)
    if not account_data:
        account_data = {}
    account = account_data.get("response", account_data)

    old_used = account.get("userTraffic", {}).get("usedTrafficBytes", 0) or 0
    old_total = account.get("trafficLimitBytes", 0) or 0
    old_expire = account.get("expireAt")

    old_gb = round((old_total - old_used) / (1024**3), 2) if old_total > 0 else 0
    old_days = 0
    if old_expire:
        try:
            exp = datetime.fromisoformat(old_expire.replace("Z", "+00:00"))
            old_days = max(0, (exp - datetime.now(timezone.utc)).days)
        except:
            old_days = 0

    expire_datetime = datetime.now(timezone.utc) + timedelta(days=pkg.days)
    expire_str = expire_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    volume_bytes = pkg.volume_gb * (1024**3)

    result = await reset_and_set_user_package(uuid, volume_bytes, expire_str)

    new_gb = pkg.volume_gb
    new_days = pkg.days

    await call.message.edit_text(
        f"✅ <b>{'خرید با موفقیت انجام شد!' if lang == 'fa' else 'Purchase successful!'}</b>\n\n"
        f"<b>{'بسته:' if lang == 'fa' else 'Package:'} {pkg.name}</b>\n"
        f"<b>{'حجم جدید:' if lang == 'fa' else 'New Volume:'} {new_gb} GB</b>\n"
        f"<b>{'مدت جدید:' if lang == 'fa' else 'New Duration:'} {new_days} {'روز' if lang == 'fa' else 'days'}</b>\n\n"
        f"{'از حالا می‌توانید از اکانت خود استفاده کنید.' if lang == 'fa' else 'You can now use your account.'}\n"
        f"{'موجودی باقیمانده:' if lang == 'fa' else 'Remaining Balance:'} {user.balance:,} {'تومان' if lang == 'fa' else 'Toman'}",
        reply_markup=main_menu_kb(lang),
        parse_mode="HTML",
    )

    if cfg.admin_group_id:
        username = f"@{user.username}" if user.username else "—"
        user_full_name = user.full_name or "—"

        admin_text = (
            f"🛒 <b>خرید جدید از کیف پول</b>\n"
            f"──────────────────\n"
            f"👤 <b>کاربر:</b> {user_full_name} ({user.telegram_id})\n"
            f"🛍️ <b>پلن:</b> {pkg.name}\n"
            f"💰 <b>هزینه:</b> {pkg.price:,} تومان\n"
            f"💳 <b>موجودی:</b> {user.balance:,} تومان\n"
            f"──────────────────\n"
            f"📊 <b>وضعیت قبل از خرید</b>\n"
            f" {username}: {old_gb} GB | {old_days} روز\n\n"
            f"📊 <b>وضعیت پس از خرید</b>\n"
            f" {username}: {new_gb} GB | {new_days} روز"
        )

        try:
            await bot.send_message(
                chat_id=cfg.admin_group_id,
                text=admin_text,
                message_thread_id=getattr(cfg, "payment_receipts_topic_id", None),
                parse_mode="HTML",
            )
        except Exception as e:
            import structlog

            log = structlog.get_logger()
            log.error(f"Failed to send purchase notification to admin: {e}")


@router.callback_query(F.data == "admin:user:add")
async def cb_admin_user_add(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await state.set_state(Admin.waiting_for_username)
    msg = await call.message.edit_text(
        f"➕ <b>{'افزودن کاربر جدید' if lang == 'fa' else 'Add New User'}</b>\n\n"
        f"{'1/5 - لطفاً نام کاربری را وارد کنید:' if lang == 'fa' else '1/5 - Please enter username:'}\n"
        f"{'(حروف انگلیسی، اعداد، - و _)' if lang == 'fa' else '(English letters, numbers, - and _)'}",
        reply_markup=back_to_menu_kb(lang),
        parse_mode="HTML",
    )
    await state.update_data(bot_message_id=msg.message_id)


@router.message(Admin.waiting_for_username)
async def handle_admin_username(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    username = message.text.strip()

    if len(username) < 3 or len(username) > 36:
        await message.answer(
            f"⚠️ {'نام کاربری باید 3 تا 36 کاراکتر باشد.' if lang == 'fa' else 'Username must be 3-36 characters.'}",
            reply_markup=back_to_menu_kb(lang),
        )
        return

    data = await state.get_data()
    bot_msg_id = data.get("bot_message_id", message.message_id)

    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    await state.update_data(
        username=username, telegram_id=None, volume_gb=None, days=None, squads=[]
    )
    await state.set_state(Admin.waiting_for_telegram_id)

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_msg_id,
        text=f"➕ <b>{'افزودن کاربر جدید' if lang == 'fa' else 'Add New User'}</b>\n\n"
        f"{'2/5 - آیدی تلگرام (اختیاری):' if lang == 'fa' else '2/5 - Telegram ID (optional):'}\n"
        f"{'یا /skip را بزنید برای رد کردن' if lang == 'fa' else 'Or type /skip to skip'}",
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

    if message.text.strip().lower() == "/skip":
        telegram_id = None
    else:
        try:
            telegram_id = int(message.text.strip())
        except ValueError:
            await message.answer(
                f"⚠️ {'لطفاً عدد معتبر وارد کنید.' if lang == 'fa' else 'Please enter a valid number.'}",
                reply_markup=back_to_menu_kb(lang),
            )
            return

    data = await state.get_data()
    bot_msg_id = data.get("bot_message_id", message.message_id)

    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    data["telegram_id"] = telegram_id
    await state.update_data(data)

    await state.set_state(Admin.waiting_for_volume)

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_msg_id,
        text=f"➕ <b>{'افزودن کاربر جدید' if lang == 'fa' else 'Add New User'}</b>\n\n"
        f"{'3/5 - حجم به گیگابایت (مثلاً 10):' if lang == 'fa' else '3/5 - Volume in GB (e.g., 10):'}\n"
        f"{'0 برای نامحدود' if lang == 'fa' else '0 for unlimited'}",
        reply_markup=back_to_menu_kb(lang),
        parse_mode="HTML",
    )


@router.message(Admin.waiting_for_volume)
async def handle_admin_volume(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    try:
        volume_gb = int(message.text.strip())
        if volume_gb < 0:
            raise ValueError()
    except ValueError:
        await message.answer(
            f"⚠️ {'لطفاً عدد معتبر وارد کنید.' if lang == 'fa' else 'Please enter a valid number.'}",
            reply_markup=back_to_menu_kb(lang),
        )
        return

    data = await state.get_data()
    bot_msg_id = data.get("bot_message_id", message.message_id)

    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    data["volume_gb"] = volume_gb
    await state.update_data(data)

    await state.set_state(Admin.waiting_for_days)

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_msg_id,
        text=f"➕ <b>{'افزودن کاربر جدید' if lang == 'fa' else 'Add New User'}</b>\n\n"
        f"{'4/5 - مدت زمان به روز (مثلاً 30):' if lang == 'fa' else '4/5 - Duration in days (e.g., 30):'}",
        reply_markup=back_to_menu_kb(lang),
        parse_mode="HTML",
    )


@router.message(Admin.waiting_for_days)
async def handle_admin_days(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError()
    except ValueError:
        await message.answer(
            f"⚠️ {'لطفاً عدد معتبر وارد کنید.' if lang == 'fa' else 'Please enter a valid number.'}",
            reply_markup=back_to_menu_kb(lang),
        )
        return

    data = await state.get_data()
    bot_msg_id = data.get("bot_message_id", message.message_id)

    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    squads = await get_internal_squads()

    data["days"] = days
    await state.update_data(data)

    if not squads:
        await _create_remnawave_user_final(message, bot, state, lang, data, [], bot_msg_id)
        return

    data["squads"] = squads
    await state.update_data(data)

    await state.set_state(Admin.waiting_for_squads)
    lines = [
        f"➕ <b>{'افزودن کاربر جدید' if lang == 'fa' else 'Add New User'}</b>\n\n"
        f"{'5/5 - انتخاب Internal Squads:' if lang == 'fa' else '5/5 - Select Internal Squads:'}\n"
    ]
    for i, squad in enumerate(squads):
        name = squad.get("name", "Unknown")
        lines.append(f"{i + 1}. {name}")

    lines.append(
        f"\n{'شماره‌ها را با کاما جدا کنید (مثلاً 1,3,5)' if lang == 'fa' else 'Enter numbers separated by comma (e.g., 1,3,5)'}"
    )
    lines.append(f"{'یا 0 برای هیچ‌کدام' if lang == 'fa' else 'Or 0 for none'}")

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_msg_id,
        text="\n".join(lines),
        reply_markup=back_to_menu_kb(lang),
        parse_mode="HTML",
    )


async def _create_remnawave_user_final(
    message: Message,
    bot: Bot,
    state: FSMContext,
    lang: str,
    data: dict,
    selected_indices: list[int],
    bot_msg_id: int | None = None,
) -> None:
    squads = data.get("squads", [])
    selected_squads = [squads[i - 1].get("uuid") for i in selected_indices if 0 < i <= len(squads)]

    volume_bytes = (data.get("volume_gb") or 0) * 1024 * 1024 * 1024

    from datetime import datetime, timedelta

    days = data.get("days") or 30
    expire_at = (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"

    result = await create_remnawave_user(
        username=data.get("username"),
        telegram_id=data.get("telegram_id"),
        traffic_limit_bytes=volume_bytes,
        expire_at=expire_at,
        squads=selected_squads if selected_squads else None,
    )

    if bot_msg_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass

    if result:
        await message.answer(
            f"✅ <b>{'کاربر با موفقیت ایجاد شد!' if lang == 'fa' else 'User created successfully!'}</b>\n\n"
            f"👤 Username: <code>{data.get('username')}</code>\n"
            f"🆔 UUID: <code>{result.get('uuid')}</code>\n"
            f"🔗 Subscription: <code>{result.get('subscriptionUrl', 'N/A')}</code>",
            reply_markup=admin_users_kb(lang),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"❌ <b>{'خطا در ایجاد کاربر' if lang == 'fa' else 'Error creating user'}</b>",
            reply_markup=admin_users_kb(lang),
            parse_mode="HTML",
        )

    await state.clear()


@router.message(Admin.waiting_for_squads)
async def handle_admin_squads(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    user = await _get_user(session, message.from_user.id)
    lang = user.lang if user else "en"

    if message.from_user.id not in cfg.admin_ids:
        return

    text = message.text.strip()

    if text == "0" or text.lower() == "/skip":
        selected_indices = []
    else:
        try:
            selected_indices = [int(x.strip()) for x in text.split(",") if x.strip()]
            if any(i < 0 for i in selected_indices):
                raise ValueError()
        except ValueError:
            await message.answer(
                f"⚠️ {'لطفاً اعداد معتبر وارد کنید.' if lang == 'fa' else 'Please enter valid numbers.'}",
                reply_markup=back_to_menu_kb(lang),
            )
            return

    data = await state.get_data()
    bot_msg_id = data.get("bot_message_id")
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    await _create_remnawave_user_final(
        message, bot, state, lang, data, selected_indices, bot_msg_id
    )


@router.callback_query(F.data == "admin:user:list")
async def cb_admin_user_list(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await _show_remnawave_user_list(call, session, lang, page=0)


async def _show_remnawave_user_list(
    call: CallbackQuery, session: AsyncSession, lang: str, page: int = 0
) -> None:
    page_size = 20

    if page < 0:
        page = 0

    result = await remnawave.get_all_users(page=page + 1, per_page=page_size)

    if result is None or result[0] is None:
        await call.message.edit_text(
            f"❌ <b>{'خطا در دریافت کاربران' if lang == 'fa' else 'Error fetching users'}</b>\n\n"
            f"{'لطفاً API Token را بررسی کنید.' if lang == 'fa' else 'Please check your API Token.'}",
            reply_markup=admin_users_kb(lang),
            parse_mode="HTML",
        )
        return

    all_users, total_count = result

    if all_users is None:
        all_users = []

    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    if page >= total_pages and total_pages > 0:
        page = total_pages - 1
        result = await remnawave.get_all_users(page=page + 1, per_page=page_size)
        if result[0]:
            all_users = result[0]

    page_users = all_users

    if not all_users:
        await call.message.edit_text(
            f"📋 <b>{'لیست کاربران' if lang == 'fa' else 'User List'}</b>\n\n{'کاربری یافت نشد.' if lang == 'fa' else 'No users found.'}",
            reply_markup=admin_users_kb(lang),
            parse_mode="HTML",
        )
        return

    lines = [f"📋 <b>{'لیست کاربران پنل' if lang == 'fa' else 'Panel User List'}</b>\n"]
    lines.append(
        f"{'صفحه' if lang == 'fa' else 'Page'} {page + 1} / {total_pages} | {'تعداد کل' if lang == 'fa' else 'Total'}: {total_count}\n"
    )

    for u in page_users:
        username = u.get("username", "—")
        status = u.get("status", "UNKNOWN")
        status_icon = "✅" if status == "ACTIVE" else "❌"
        lines.append(f"{status_icon} {username}")

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
    await _show_remnawave_user_list(call, session, lang, page=page)


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


@router.callback_query(F.data == "admin:stats:online")
async def cb_admin_stats_online(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    all_users_result = await remnawave.get_all_users(page=1, per_page=200)
    if not all_users_result or not all_users_result[0]:
        await call.message.edit_text(
            f"🟢 <b>{'کاربران آنلاین (۵ دقیقه تا ۱ روز)' if lang == 'fa' else 'Online Users (5min - 1 day)'}</b>\n\n"
            f"{'کاربری یافت نشد' if lang == 'fa' else 'No users found'}",
            reply_markup=admin_stats_back_kb(lang),
            parse_mode="HTML",
        )
        return

    all_users = all_users_result[0]
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    online_users = []

    for u in all_users:
        user_traffic = u.get("userTraffic", {})
        online_at = user_traffic.get("onlineAt")

        if not online_at:
            continue

        try:
            online_time = datetime.fromisoformat(online_at.replace("Z", "+00:00"))
            diff = now - online_time
            diff_hours = diff.total_seconds() / 3600

            if 5 / 60 <= diff_hours < 24:
                expire_at = u.get("expireAt")
                days_left = "—"
                if expire_at:
                    try:
                        expire_time = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
                        days_left = (expire_time - now).days
                        days_left = max(0, days_left)
                    except:
                        pass
                online_users.append(
                    {
                        "username": u.get("username", "—"),
                        "uuid": u.get("uuid"),
                        "online_at": online_at,
                        "hours_ago": round(diff_hours, 1),
                        "days_left": days_left,
                    }
                )
        except:
            continue

    if not online_users:
        await call.message.edit_text(
            f"🟢 <b>{'کاربران آنلاین (۵ دقیقه تا ۱ روز)' if lang == 'fa' else 'Online Users (5min - 1 day)'}</b>\n\n"
            f"{'کاربری یافت نشد' if lang == 'fa' else 'No users found'}",
            reply_markup=admin_stats_back_kb(lang),
            parse_mode="HTML",
        )
        return

    page = 0
    page_size = 40
    start = page * page_size
    page_users = online_users[start : start + page_size]

    lines = [
        f"🟢 <b>{'کاربران آنلاین (۵ دقیقه تا ۱ روز)' if lang == 'fa' else 'Online Users (5min - 1 day)'}</b>\n"
    ]
    lines.append(f"{'تعداد کل: ' if lang == 'fa' else 'Total: '}{len(online_users)}\n")

    for i, u in enumerate(page_users, start + 1):
        username = u.get("username", "—")
        days_left = u.get("days_left", "—")
        daily_usage = 0
        lines.append(f"{i}. {username} | {daily_usage} | {days_left}")

    kb_buttons = []
    if len(online_users) > page_size:
        kb_buttons.append(
            [InlineKeyboardButton(text="➡️ بعدی", callback_data=f"admin:stats:online:1")]
        )
    kb_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:stats")])

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:stats:online:"))
async def cb_admin_stats_online_page(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = int(call.data.split(":")[-1])
    page_size = 40

    all_users_result = await remnawave.get_all_users(page=1, per_page=200)
    if not all_users_result or not all_users_result[0]:
        return

    all_users = all_users_result[0]
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    online_users = []

    for u in all_users:
        user_traffic = u.get("userTraffic", {})
        online_at = user_traffic.get("onlineAt")

        if not online_at:
            continue

        try:
            online_time = datetime.fromisoformat(online_at.replace("Z", "+00:00"))
            diff = now - online_time
            diff_hours = diff.total_seconds() / 3600

            if diff_hours < 24:
                expire_at = u.get("expireAt")
                days_left = "—"
                if expire_at:
                    try:
                        expire_time = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
                        days_left = (expire_time - now).days
                        days_left = max(0, days_left)
                    except:
                        pass
                online_users.append(
                    {
                        "username": u.get("username", "—"),
                        "uuid": u.get("uuid"),
                        "online_at": online_at,
                        "hours_ago": round(diff_hours, 1),
                        "days_left": days_left,
                    }
                )
        except:
            continue

    start = page * page_size
    page_users = online_users[start : start + page_size]

    lines = [
        f"🟢 <b>{'کاربران آنلاین (۵ دقیقه تا ۱ روز)' if lang == 'fa' else 'Online Users (5min - 1 day)'}</b>\n"
    ]
    lines.append(f"{'تعداد کل: ' if lang == 'fa' else 'Total: '}{len(online_users)}\n")

    for i, u in enumerate(page_users, start + 1):
        username = u.get("username", "—")
        days_left = u.get("days_left", "—")
        daily_usage = 0
        lines.append(f"{i}. {username} | {daily_usage} | {days_left}")

    kb_buttons = []
    if start + page_size < len(online_users):
        kb_buttons.append(
            [InlineKeyboardButton(text="➡️ بعدی", callback_data=f"admin:stats:online:{page + 1}")]
        )
    if page > 0:
        kb_buttons.append(
            [InlineKeyboardButton(text="➡️ قبلی", callback_data=f"admin:stats:online:{page - 1}")]
        )
    kb_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:stats")])

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:stats:online_now")
async def cb_admin_stats_online_now(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = 0
    await show_online_now_users(call, lang, page)


@router.callback_query(F.data.startswith("admin:stats:online_now:"))
async def cb_admin_stats_online_now_page(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = int(call.data.split(":")[-1])
    await show_online_now_users(call, lang, page)


async def show_online_now_users(call: CallbackQuery, lang: str, page: int) -> None:
    from datetime import datetime, timezone

    page_size = 40
    all_users_result = await remnawave.get_all_users(page=1, per_page=200)
    if not all_users_result or not all_users_result[0]:
        await call.message.edit_text(
            f"🟢 <b>{'کاربران آنلاین (همین الان)' if lang == 'fa' else 'Online Users (Now)'}</b>\n\n"
            f"{'کاربری یافت نشد' if lang == 'fa' else 'No users found'}",
            reply_markup=admin_stats_back_kb(lang),
            parse_mode="HTML",
        )
        return

    all_users = all_users_result[0]
    now = datetime.now(timezone.utc)
    online_users = []

    for u in all_users:
        user_traffic = u.get("userTraffic", {})
        online_at = user_traffic.get("onlineAt")

        if not online_at:
            continue

        try:
            online_time = datetime.fromisoformat(online_at.replace("Z", "+00:00"))
            diff = now - online_time
            diff_minutes = diff.total_seconds() / 60

            if diff_minutes < 5:
                expire_at = u.get("expireAt")
                days_left = "—"
                if expire_at:
                    try:
                        expire_time = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
                        days_left = (expire_time - now).days
                        days_left = max(0, days_left)
                    except:
                        pass
                online_users.append(
                    {
                        "username": u.get("username", "—"),
                        "uuid": u.get("uuid"),
                        "online_at": online_at,
                        "mins_ago": round(diff_minutes, 1),
                        "days_left": days_left,
                    }
                )
        except:
            continue

    if not online_users:
        await call.message.edit_text(
            f"🟢 <b>{'کاربران آنلاین (همین الان)' if lang == 'fa' else 'Online Users (Now)'}</b>\n\n"
            f"{'کاربری یافت نشد' if lang == 'fa' else 'No users found'}",
            reply_markup=admin_stats_back_kb(lang),
            parse_mode="HTML",
        )
        return

    start = page * page_size
    page_users = online_users[start : start + page_size]

    lines = [
        f"🟢 <b>{'کاربران آنلاین (همین الان)' if lang == 'fa' else 'Online Users (Now)'}</b>\n"
    ]
    lines.append(f"{'تعداد کل: ' if lang == 'fa' else 'Total: '}{len(online_users)}\n")

    for i, u in enumerate(page_users, start + 1):
        username = u.get("username", "—")
        days_left = u.get("days_left", "—")
        daily_usage = 0
        lines.append(f"{i}. {username} | {daily_usage} | {days_left}")

    kb_buttons = []
    if start + page_size < len(online_users):
        kb_buttons.append(
            [
                InlineKeyboardButton(
                    text="➡️ بعدی", callback_data=f"admin:stats:online_now:{page + 1}"
                )
            ]
        )
    if page > 0:
        kb_buttons.append(
            [
                InlineKeyboardButton(
                    text="➡️ قبلی", callback_data=f"admin:stats:online_now:{page - 1}"
                )
            ]
        )
    kb_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:stats")])

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:stats:inactive_7d")
async def cb_admin_stats_inactive_7d(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = 0
    await show_inactive_users(call, lang, page)


@router.callback_query(F.data.startswith("admin:stats:inactive_7d:"))
async def cb_admin_stats_inactive_7d_page(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = int(call.data.split(":")[-1])
    await show_inactive_users(call, lang, page)


async def show_inactive_users(call: CallbackQuery, lang: str, page: int) -> None:
    from datetime import datetime, timezone

    page_size = 40
    all_users_result = await remnawave.get_all_users(page=1, per_page=200)
    if not all_users_result or not all_users_result[0]:
        await call.message.edit_text(
            f"🟡 <b>{'کاربران غیرفعال 1 تا 7 روز' if lang == 'fa' else 'Inactive Users (1-7 days)'}</b>\n\n"
            f"{'کاربری یافت نشد' if lang == 'fa' else 'No users found'}",
            reply_markup=admin_stats_back_kb(lang),
            parse_mode="HTML",
        )
        return

    all_users = all_users_result[0]
    now = datetime.now(timezone.utc)
    inactive_users = []

    for u in all_users:
        user_traffic = u.get("userTraffic", {})
        online_at = user_traffic.get("onlineAt")

        if not online_at:
            continue

        try:
            online_time = datetime.fromisoformat(online_at.replace("Z", "+00:00"))
            diff = now - online_time
            diff_hours = diff.total_seconds() / 3600

            if 24 <= diff_hours < 24 * 7:
                inactive_users.append(
                    {
                        "username": u.get("username", "—"),
                        "uuid": u.get("uuid"),
                        "online_at": online_at,
                        "days_ago": round(diff_hours / 24, 1),
                    }
                )
        except:
            continue

    if not inactive_users:
        await call.message.edit_text(
            f"🟡 <b>{'کاربران غیرفعال 1 تا 7 روز' if lang == 'fa' else 'Inactive Users (1-7 days)'}</b>\n\n"
            f"{'کاربری یافت نشد' if lang == 'fa' else 'No users found'}",
            reply_markup=admin_stats_back_kb(lang),
            parse_mode="HTML",
        )
        return

    start = page * page_size
    page_users = inactive_users[start : start + page_size]

    lines = [
        f"🟡 <b>{'کاربران غیرفعال 1 تا 7 روز' if lang == 'fa' else 'Inactive Users (1-7 days)'}</b>\n"
    ]
    lines.append(f"{'تعداد کل: ' if lang == 'fa' else 'Total: '}{len(inactive_users)}\n")

    for i, u in enumerate(page_users, start + 1):
        days = u.get("days_ago", 0)
        time_str = f"{days} روز پیش" if lang == "fa" else f"{days}d ago"
        lines.append(f"{i}. 👤 {u['username']} ({time_str})")

    kb_buttons = []
    if start + page_size < len(inactive_users):
        kb_buttons.append(
            [
                InlineKeyboardButton(
                    text="➡️ بعدی", callback_data=f"admin:stats:inactive_7d:{page + 1}"
                )
            ]
        )
    if page > 0:
        kb_buttons.append(
            [
                InlineKeyboardButton(
                    text="➡️ قبلی", callback_data=f"admin:stats:inactive_7d:{page - 1}"
                )
            ]
        )
    kb_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:stats")])

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:stats:never")
async def cb_admin_stats_never(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = 0
    await show_never_connected_users(call, lang, page)


@router.callback_query(F.data.startswith("admin:stats:never:"))
async def cb_admin_stats_never_page(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = int(call.data.split(":")[-1])
    await show_never_connected_users(call, lang, page)


async def show_never_connected_users(call: CallbackQuery, lang: str, page: int) -> None:
    page_size = 40
    all_users_result = await remnawave.get_all_users(page=1, per_page=200)
    if not all_users_result or not all_users_result[0]:
        await call.message.edit_text(
            f"🔴 <b>{'کاربرانی که هرگز متصل نشده‌اند' if lang == 'fa' else 'Never Connected Users'}</b>\n\n"
            f"{'کاربری یافت نشد' if lang == 'fa' else 'No users found'}",
            reply_markup=admin_stats_back_kb(lang),
            parse_mode="HTML",
        )
        return

    all_users = all_users_result[0]
    never_connected_users = []

    for u in all_users:
        user_traffic = u.get("userTraffic", {})
        first_connected_at = user_traffic.get("firstConnectedAt")

        if first_connected_at is None:
            never_connected_users.append(
                {
                    "username": u.get("username", "—"),
                    "uuid": u.get("uuid"),
                    "email": u.get("email", "—"),
                    "created_at": u.get("createdAt", "—"),
                }
            )

    if not never_connected_users:
        await call.message.edit_text(
            f"🔴 <b>{'کاربرانی که هرگز متصل نشده‌اند' if lang == 'fa' else 'Never Connected Users'}</b>\n\n"
            f"{'کاربری یافت نشد' if lang == 'fa' else 'No users found'}",
            reply_markup=admin_stats_back_kb(lang),
            parse_mode="HTML",
        )
        return

    start = page * page_size
    page_users = never_connected_users[start : start + page_size]

    lines = [
        f"🔴 <b>{'کاربرانی که هرگز متصل نشده‌اند' if lang == 'fa' else 'Never Connected Users'}</b>\n"
    ]
    lines.append(f"{'تعداد کل: ' if lang == 'fa' else 'Total: '}{len(never_connected_users)}\n")

    for i, u in enumerate(page_users, start + 1):
        username = u["username"]
        email = u.get("email", "—")
        lines.append(f"{i}. 👤 {username} ({email})")

    kb_buttons = []
    if start + page_size < len(never_connected_users):
        kb_buttons.append(
            [InlineKeyboardButton(text="➡️ بعدی", callback_data=f"admin:stats:never:{page + 1}")]
        )
    if page > 0:
        kb_buttons.append(
            [InlineKeyboardButton(text="➡️ قبلی", callback_data=f"admin:stats:never:{page - 1}")]
        )
    kb_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:stats")])

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
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


@router.callback_query(F.data == "admin:stats:bot_users")
async def cb_admin_stats_bot_users(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    await _show_bot_user_list(call, session, lang, page=0)


async def _show_bot_user_list(
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
            f"📋 <b>{'لیست کاربران ربات' if lang == 'fa' else 'Bot User List'}</b>\n\n{'کاربری یافت نشد.' if lang == 'fa' else 'No users found.'}",
            reply_markup=admin_stats_kb(lang),
            parse_mode="HTML",
        )
        return

    lines = [f"📋 <b>{'لیست کاربران ربات' if lang == 'fa' else 'Bot User List'}</b>\n"]
    lines.append(
        f"{'صفحه' if lang == 'fa' else 'Page'} {page + 1} / {total_pages} | {'تعداد کل' if lang == 'fa' else 'Total'}: {total_count}\n"
    )

    for u in users:
        status = "✅" if u.is_registered else "❌"
        username = f"@{u.username}" if u.username else "—"
        balance_text = f"{u.balance:,}"
        lines.append(f"{status} {u.telegram_id} | {username} | 💰 {balance_text}")

    text = "\n".join(lines)
    await call.message.edit_text(
        text,
        reply_markup=admin_user_list_kb(page, total_pages, lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:stats:bot_users:"))
async def cb_admin_stats_bot_users_page(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = int(call.data.split(":")[-1])
    await _show_bot_user_list(call, session, lang, page=page)


@router.callback_query(F.data == "admin:stats:balances")
async def cb_admin_stats_balances(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = 0
    await show_user_balances(call, session, lang, page)


@router.callback_query(F.data.startswith("admin:stats:balances:"))
async def cb_admin_stats_balances_page(call: CallbackQuery, session: AsyncSession) -> None:
    user = await _get_user(session, call.from_user.id)
    lang = user.lang if user else "en"
    await call.answer()

    if call.from_user.id not in cfg.admin_ids:
        return

    page = int(call.data.split(":")[-1])
    await show_user_balances(call, session, lang, page)


async def show_user_balances(
    call: CallbackQuery, session: AsyncSession, lang: str, page: int
) -> None:
    page_size = 40

    result = await session.execute(select(func.sum(User.balance)))
    total_balance = result.scalar() or 0

    result = await session.execute(select(func.count(User.id)).where(User.balance > 0))
    count_with_balance = result.scalar() or 0

    result = await session.execute(
        select(User)
        .where(User.balance > 0)
        .order_by(User.balance.desc())
        .limit(page_size)
        .offset(page * page_size)
    )
    users_with_balance = result.scalars().all()

    lines = [f"💰 <b>{'موجودی کاربران' if lang == 'fa' else 'User Balances'}</b>\n"]
    lines.append(
        f"{'کل موجودی' if lang == 'fa' else 'Total Balance'}: {total_balance:,} {'تومان' if lang == 'fa' else 'Toman'}\n"
    )

    if users_with_balance:
        lines.append(f"\n{'کاربران با موجودی:' if lang == 'fa' else 'Users with balance:'}")
        lines.append(f"{'تعداد' if lang == 'fa' else 'Count'}: {count_with_balance}\n")

        for i, u in enumerate(users_with_balance, start=page * page_size + 1):
            username = f"@{u.username}" if u.username else "—"
            balance_text = f"{u.balance:,}"
            lines.append(f"{i}. {username} | 💰 {balance_text}")

    text = "\n".join(lines)

    kb_buttons = []
    if count_with_balance > (page + 1) * page_size:
        kb_buttons.append(
            [InlineKeyboardButton(text="➡️ بعدی", callback_data=f"admin:stats:balances:{page + 1}")]
        )
    if page > 0:
        kb_buttons.append(
            [InlineKeyboardButton(text="➡️ قبلی", callback_data=f"admin:stats:balances:{page - 1}")]
        )
    kb_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:stats")])

    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
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
