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
                InlineKeyboardButton(text=t(lang, "btn_main_stats"), callback_data="menu:stats"),
                InlineKeyboardButton(
                    text=t(lang, "btn_main_account"), callback_data="menu:account"
                ),
            ],
            [
                InlineKeyboardButton(text=t(lang, "btn_main_wallet"), callback_data="menu:wallet"),
                InlineKeyboardButton(
                    text=t(lang, "btn_main_services"), callback_data="menu:services"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_main_tutorial"), callback_data="menu:tutorial"
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_main_settings"), callback_data="menu:settings"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_main_support"), callback_data="menu:support"
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_main_profile"), callback_data="menu:profile"
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
