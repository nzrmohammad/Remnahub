from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.core.i18n import t


def lang_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇮🇷 فارسی", callback_data="lang:fa"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            ]
        ]
    )


def auth_menu_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "btn_login"), callback_data="auth:login"),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_new_service"), callback_data="auth:new_service"
                ),
            ],
        ]
    )


def back_to_auth_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="auth:back")]
        ]
    )


def main_menu_kb(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_main_account"), callback_data="menu:account"
                ),
                InlineKeyboardButton(text=t(lang, "btn_main_stats"), callback_data="menu:stats"),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_main_services"), callback_data="menu:services"
                ),
                InlineKeyboardButton(text=t(lang, "btn_main_wallet"), callback_data="menu:wallet"),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_main_settings"), callback_data="menu:settings"
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_main_tutorial"), callback_data="menu:tutorial"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_main_profile"), callback_data="menu:profile"
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_main_support"), callback_data="menu:support"
                ),
            ],
            [
                InlineKeyboardButton(text=t(lang, "btn_main_panel"), callback_data="menu:panel"),
            ],
        ]
    )
    return kb


def back_to_menu_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:back")]
        ]
    )


def settings_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_change_lang"), callback_data="settings:change_lang"
                )
            ],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:back")],
        ]
    )


def account_list_kb(accounts: list[dict], lang: str) -> InlineKeyboardMarkup:
    kb = []
    for account in accounts:
        username = account.get("username", "—")
        status = account.get("status", "")
        status_icon = "✅" if status == "ACTIVE" else "❌"
        kb.append(
            [
                InlineKeyboardButton(
                    text=f"👤 {username} ({status_icon} {'فعال' if status == 'ACTIVE' else 'غیرفعال'})",
                    callback_data=f"account:{account.get('uuid')}",
                )
            ]
        )
    kb.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def account_detail_kb(uuid: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔗 دریافت لینک", callback_data=f"account:link:{uuid}"),
                InlineKeyboardButton(
                    text="💳 سابقه پرداخت", callback_data=f"account:payment:{uuid}"
                ),
            ],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="account:list")],
        ]
    )


def wallet_main_kb(lang: str, balance: int = 0) -> InlineKeyboardMarkup:
    balance_text = f"{balance:,}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"💰 {balance_text} تومان", callback_data="wallet:balance")],
            [
                InlineKeyboardButton(text="📜 تاریخچه تراکنش‌ها", callback_data="wallet:history"),
                InlineKeyboardButton(text="➕ شارژ حساب", callback_data="wallet:charge"),
            ],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:back")],
        ]
    )


def wallet_cancel_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو عملیات", callback_data="wallet:cancel")]
        ]
    )


def wallet_payment_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو عملیات", callback_data="wallet:cancel")]
        ]
    )


def wallet_success_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💼 بازگشت به کیف پول", callback_data="menu:wallet"),
                InlineKeyboardButton(text="📡 مشاهده سرویس‌ها", callback_data="menu:services"),
            ]
        ]
    )


def admin_approve_reject_kb(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید", callback_data=f"wallet:approve:{request_id}"),
                InlineKeyboardButton(text="❌ رد", callback_data=f"wallet:reject:{request_id}"),
            ]
        ]
    )


def stats_navigation_kb(current_index: int, total: int, uuid: str) -> InlineKeyboardMarkup:
    kb = []
    nav_buttons = []
    if current_index > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"stats:nav:{current_index - 1}")
        )
    if current_index < total - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="بعدی ➡️", callback_data=f"stats:nav:{current_index + 1}")
        )
    if nav_buttons:
        kb.append(nav_buttons)
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_main_kb(lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 مدیریت کاربران", callback_data="admin:users"),
                InlineKeyboardButton(text="📊 گزارش‌ها و آمار", callback_data="admin:stats"),
            ],
            [
                InlineKeyboardButton(text="💾 پشتیبان‌گیری", callback_data="admin:backup"),
            ],
            [
                InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="menu:back"),
            ],
        ]
    )


def admin_users_kb(lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ افزودن کاربر جدید", callback_data="admin:user:add"),
                InlineKeyboardButton(text="📋 لیست کاربران", callback_data="admin:user:list"),
            ],
            [
                InlineKeyboardButton(text="🔍 جستجوی کاربر", callback_data="admin:user:search"),
            ],
            [
                InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:panel"),
            ],
        ]
    )


def admin_stats_kb(lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🟢 آنلاین 24 ساعت اخیر", callback_data="admin:stats:active_24h"
                ),
                InlineKeyboardButton(
                    text="🟡 غیرفعال 1 تا 7 روز", callback_data="admin:stats:inactive_7d"
                ),
            ],
            [
                InlineKeyboardButton(text="🔴 هرگز متصل نشده", callback_data="admin:stats:never"),
                InlineKeyboardButton(
                    text="👥 لیست کاربران ربات", callback_data="admin:stats:all_users"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💰 موجودی کاربران", callback_data="admin:stats:balances"
                ),
            ],
            [
                InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:panel"),
            ],
        ]
    )


def admin_user_list_kb(page: int, total_pages: int, lang: str = "fa") -> InlineKeyboardMarkup:
    kb = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"admin:user:list:{page - 1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="بعدی ➡️", callback_data=f"admin:user:list:{page + 1}")
        )
    if nav_buttons:
        kb.append(nav_buttons)
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:users")])
    return InlineKeyboardMarkup(inline_keyboard=kb)
