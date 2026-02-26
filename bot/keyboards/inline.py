from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.core.i18n import t


RULES_TEXT_FA = """📜 <b>قوانین و شرایط استفاده</b>

لطفاً قوانین را با دقت مطالعه کنید:

1️⃣ سرویس دارای تست میباشد لطفا قبل از خرید به صورت رایگان تست بگیرید.

2️⃣ در صورتی که بدون تست کردن سرویس خرید انجام شود و کاربر ناراضی باشد متاسفانه امکان بازگشت وجه وجود ندارد.

3️⃣ در صورت اختلال فقط به اطلاعیه های کانال توجه فرمایید در غیر این صورت سرویس فاقد پشتیبانی میباشد.

4️⃣ هرگونه مشکلی که روی سرویس ها یا سوالی دارید داخل یک پیام همراه با شناسه کاربری ارسال کنید در غیر این صورت هیچگونه پاسخی از سمت پشتیبانی دریافت نخواهد شد.

5️⃣ هرگونه بی احترامی باعث لغو سرویس و عدم بازگشت وجه خواهد شد.

6️⃣ تایم پشتیبانی از ساعت 10 صبح الی 12 شب هست و اگر کاربری خارج از تایم پشتیبانی پیام ارسال کند در تایم پشتیبانی پاسخ داده خواهد شد.

7️⃣ عدم رعایت قوانین باعث حذف سرویس و عدم پشتیبانی خواهد بود."""


RULES_TEXT_EN = """📜 <b>Terms and Conditions</b>

Please read the rules carefully:

1️⃣ The service has a free test. Please test before purchasing.

2️⃣ If you purchase without testing and are unsatisfied, unfortunately there is no refund.

3️⃣ In case of disruption, only pay attention to channel announcements. Otherwise, the service has no support.

4️⃣ Any issues or questions about services should be sent in one message with your user ID. Otherwise, you will not receive any response from support.

5️⃣ Any disrespect will result in service cancellation and no refund.

6️⃣ Support hours are from 10 AM to 12 AM. If you send messages outside support hours, you will be answered during support hours.

7️⃣ Failure to comply with the rules will result in service removal and no support."""


def rules_kb(lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ قوانین را می‌پذیرم" if lang == "fa" else "I accept the rules",
                    callback_data="rules:accept",
                )
            ],
        ]
    )


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
            [
                InlineKeyboardButton(
                    text=t(lang, "settings_warnings"), callback_data="settings:warnings"
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
                InlineKeyboardButton(text="📊 گزارش‌ها و آمار", callback_data="admin:stats"),
                InlineKeyboardButton(text="👥 مدیریت کاربران", callback_data="admin:users"),
            ],
            [
                InlineKeyboardButton(text="📦 مدیریت بسته‌ها", callback_data="admin:packages"),
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


def tutorial_os_select_kb(lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Android", callback_data="tutorial:os:android"),
                InlineKeyboardButton(text="iOS", callback_data="tutorial:os:ios"),
                InlineKeyboardButton(text="Windows", callback_data="tutorial:os:windows"),
            ],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:back")],
        ]
    )


def tutorial_app_select_kb(os: str, lang: str = "fa") -> InlineKeyboardMarkup:
    os_text = {"android": "Android", "ios": "iOS", "windows": "Windows"}.get(os, os)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Happ (پیشنهادی)", callback_data=f"tutorial:app:{os}:happ"
                )
            ],
            [InlineKeyboardButton(text="Hiddify", callback_data=f"tutorial:app:{os}:hiddify")],
            [InlineKeyboardButton(text="V2rayNG", callback_data=f"tutorial:app:{os}:v2rayng")],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="tutorial:back_to_os")],
        ]
    )


def tutorial_view_kb(lang: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_view_tutorial"), url=url)],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_back_to_apps"), callback_data="tutorial:back_to_apps"
                )
            ],
        ]
    )


def settings_warnings_kb(
    lang: str, expiry_enabled: bool = True, volume_enabled: bool = True
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅' if expiry_enabled else '⬜'} {t(lang, 'settings_expiry_warning')}",
                    callback_data="settings:warning:expiry",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{'✅' if volume_enabled else '⬜'} {t(lang, 'settings_volume_warning')}",
                    callback_data="settings:warning:volume",
                )
            ],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:back")],
        ]
    )


def admin_packages_kb(lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ افزودن بسته جدید", callback_data="admin:package:add"),
            ],
            [
                InlineKeyboardButton(text="📋 لیست بسته‌ها", callback_data="admin:package:list"),
            ],
            [
                InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:panel"),
            ],
        ]
    )


def package_list_kb(packages: list, lang: str = "fa") -> InlineKeyboardMarkup:
    kb = []
    category_icons = {
        "economy": "💰",
        "vip": "👑",
        "tunnel": "🌐",
    }
    for pkg in packages:
        status = "✅" if pkg.is_active else "❌"
        cat_icon = category_icons.get(pkg.category, "💰")
        kb.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {cat_icon} {pkg.name} - {pkg.volume_gb}GB/{pkg.days}روز",
                    callback_data=f"package:edit:{pkg.id}",
                )
            ]
        )
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:packages")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def package_edit_kb(pkg_id: int, lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ فعال کردن", callback_data=f"package:toggle:{pkg_id}:1"
                ),
                InlineKeyboardButton(
                    text="❌ غیرفعال کردن", callback_data=f"package:toggle:{pkg_id}:0"
                ),
            ],
            [
                InlineKeyboardButton(text="🗑️ حذف بسته", callback_data=f"package:delete:{pkg_id}"),
            ],
            [
                InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="admin:package:list"),
            ],
        ]
    )


def user_packages_kb(
    packages: list, lang: str = "fa", user_balance: int = 0
) -> tuple[str, InlineKeyboardMarkup]:
    if not packages:
        return (
            f"📦 <b>{'بسته‌های فروش' if lang == 'fa' else 'Available Packages'}</b>\n\n"
            f"{'در حال حاضر بسته‌ای برای فروش وجود ندارد.' if lang == 'fa' else 'No packages available for purchase at the moment.'}",
            back_to_menu_kb(lang),
        )

    category_icons = {
        "economy": "💰",
        "vip": "👑",
        "tunnel": "🌐",
    }

    header = f"🚀 <b>{'پلن‌های فروش سرویس' if lang == 'fa' else 'Service Plans'}</b>\n"
    header += f"{'💡 بسته مورد نظر خود را انتخاب کنید.' if lang == 'fa' else '💡 Select your preferred package.'}\n"
    header += "────────────────────\n"

    lines = []
    kb = []
    for pkg in packages:
        cat_icon = category_icons.get(pkg.category, "💰")
        can_buy = user_balance >= pkg.price
        status_icon = "✅" if can_buy else "❌"
        price_text = f"{pkg.price:,}"

        lines.append(
            f"{cat_icon} <b>{pkg.name}</b>\n"
            f"{'حجم:' if lang == 'fa' else 'Volume:'} {pkg.volume_gb} {'گیگابایت' if lang == 'fa' else 'GB'}\n"
            f"{'مدت زمان :' if lang == 'fa' else 'Duration:'} {pkg.days} {'روز' if lang == 'fa' else 'days'}\n"
            f"{'قیمت :' if lang == 'fa' else 'Price:'} {price_text} {'تومان' if lang == 'fa' else 'IRR'}\n"
            f"────────────────────"
        )

        btn_text = f"{status_icon} {'خرید' if lang == 'fa' else 'Buy'} {pkg.name} ({price_text} {'تومان' if lang == 'fa' else 'IRR'})"
        kb.append(
            [
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"package:buy:{pkg.id}",
                )
            ]
        )

    kb.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:back")])

    text = header + "\n\n".join(lines)

    return text, InlineKeyboardMarkup(inline_keyboard=kb)
