"""Buttons and the data they carry."""
from datetime import date, datetime, timedelta

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .db import Booking, Master, Service
from .texts import BTN_ABOUT, BTN_BOOK, BTN_MY, BTN_SKIP, fmt_day


# ---------- callback data ----------
class SvcCb(CallbackData, prefix="svc"):
    id: int


class MasterCb(CallbackData, prefix="mst"):
    id: int  # 0 = any master


class DayCb(CallbackData, prefix="day"):
    d: str  # YYYYMMDD


class TimeCb(CallbackData, prefix="tm"):
    t: str  # HHMM


class NavCb(CallbackData, prefix="nav"):
    to: str  # services | masters | days | slots | confirm | abort | book


class MyCancelCb(CallbackData, prefix="mc"):
    id: int
    step: str  # ask | yes | no


class AdmCb(CallbackData, prefix="adm"):
    action: str  # menu | day | pick | stats | broadcast | export
    d: str = ""


class AdmCancelCb(CallbackData, prefix="admc"):
    id: int
    d: str


class BcastCb(CallbackData, prefix="bc"):
    go: str  # send | cancel


# ---------- keyboards ----------
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BOOK)], [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_ABOUT)]],
        resize_keyboard=True,
    )


def phone_request() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Share my phone number", request_contact=True)],
                  [KeyboardButton(text=BTN_SKIP)]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def _back(kb: InlineKeyboardBuilder, to: str) -> None:
    kb.button(text="⬅️ Back", callback_data=NavCb(to=to))


def services_kb(services: list[Service]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        kb.button(text=f"{s.emoji} {s.name} · {s.duration_min} min · €{s.price}", callback_data=SvcCb(id=s.id))
    kb.adjust(1)
    return kb.as_markup()


def masters_kb(masters: list[Master]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✨ Any available master", callback_data=MasterCb(id=0))
    for m in masters:
        kb.button(text=f"👤 {m.name}", callback_data=MasterCb(id=m.id))
    _back(kb, "services")
    kb.adjust(1)
    return kb.as_markup()


def days_kb(days: list[date], today: date) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=fmt_day(d, today), callback_data=DayCb(d=d.strftime("%Y%m%d")))
    _back(kb, "masters")
    kb.adjust(*([2] * ((len(days) + 1) // 2)), 1)
    return kb.as_markup()


def slots_kb(slots: list[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in slots:
        kb.button(text=s.strftime("%H:%M"), callback_data=TimeCb(t=s.strftime("%H%M")))
    _back(kb, "days")
    kb.adjust(*([4] * ((len(slots) + 3) // 4)), 1)
    return kb.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Confirm booking", callback_data=NavCb(to="confirm"))
    _back(kb, "slots")
    kb.button(text="✖️ Cancel", callback_data=NavCb(to="abort"))
    kb.adjust(1, 2)
    return kb.as_markup()


def book_now_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Book now", callback_data=NavCb(to="book"))
    return kb.as_markup()


def my_bookings_kb(bookings: list[Booking]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(text=f"❌ Cancel {b.start:%d.%m %H:%M}", callback_data=MyCancelCb(id=b.id, step="ask"))
    kb.adjust(1)
    return kb.as_markup()


def cancel_confirm_kb(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Yes, cancel it", callback_data=MyCancelCb(id=booking_id, step="yes"))
    kb.button(text="No, keep it", callback_data=MyCancelCb(id=booking_id, step="no"))
    kb.adjust(2)
    return kb.as_markup()


def reminder_kb(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ I can't come — cancel", callback_data=MyCancelCb(id=booking_id, step="ask"))
    return kb.as_markup()


# ---------- owner panel ----------
def admin_menu_kb(today: date) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Today", callback_data=AdmCb(action="day", d=today.strftime("%Y%m%d")))
    kb.button(text="📋 Tomorrow", callback_data=AdmCb(action="day", d=(today + timedelta(days=1)).strftime("%Y%m%d")))
    kb.button(text="🗓 Pick a day", callback_data=AdmCb(action="pick"))
    kb.button(text="📊 Stats", callback_data=AdmCb(action="stats"))
    kb.button(text="📢 Broadcast", callback_data=AdmCb(action="broadcast"))
    kb.button(text="📤 Export CSV", callback_data=AdmCb(action="export"))
    kb.adjust(2, 2, 2)
    return kb.as_markup()


def admin_days_kb(days: list[date], today: date) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=fmt_day(d, today), callback_data=AdmCb(action="day", d=d.strftime("%Y%m%d")))
    kb.button(text="⬅️ Back", callback_data=AdmCb(action="menu"))
    kb.adjust(*([2] * ((len(days) + 1) // 2)), 1)
    return kb.as_markup()


def admin_schedule_kb(bookings: list[Booking], d: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(text=f"❌ #{b.id} {b.start:%H:%M} {b.user.full_name[:16]}", callback_data=AdmCancelCb(id=b.id, d=d))
    kb.button(text="⬅️ Back", callback_data=AdmCb(action="menu"))
    kb.adjust(1)
    return kb.as_markup()


def admin_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Back", callback_data=AdmCb(action="menu"))
    return kb.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Send", callback_data=BcastCb(go="send"))
    kb.button(text="✖️ Cancel", callback_data=BcastCb(go="cancel"))
    kb.adjust(2)
    return kb.as_markup()
