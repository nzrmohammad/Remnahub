from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class LanguageSelect(StatesGroup):
    choosing = State()


class AuthMenu(StatesGroup):
    idle = State()
    waiting_for_rules = State()
    waiting_for_lang = State()


class NewService(StatesGroup):
    waiting_for_info = State()


class MainMenu(StatesGroup):
    idle = State()


class Support(StatesGroup):
    waiting_for_message = State()


class Settings(StatesGroup):
    idle = State()


class Wallet(StatesGroup):
    idle = State()
    waiting_for_amount = State()
    waiting_for_receipt = State()


class Admin(StatesGroup):
    idle = State()
    waiting_for_telegram_id = State()
    waiting_for_search = State()


class Package(StatesGroup):
    waiting_for_name = State()
    waiting_for_volume = State()
    waiting_for_days = State()
    waiting_for_price = State()
    waiting_for_category = State()
