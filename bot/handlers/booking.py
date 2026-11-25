"""Client booking flow: service → master → day → time → confirm → (phone) → booked."""
from datetime import date, datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import texts
from ..config import Config
from ..repo import Repo
from ..slots import bookable_days
from .common import safe_send, show

router = Router(name="booking")


class Book(StatesGroup):
    flow = State()   # choosing with inline buttons
    phone = State()  # waiting for a phone number


# ---------- step views ----------
async def view_services(target: Message | CallbackQuery, state: FSMContext, repo: Repo) -> None:
    await state.set_state(Book.flow)
    await state.set_data({})
    await show(target, texts.ASK_SERVICE, kb.services_kb(await repo.services()))


async def view_masters(target: CallbackQuery, repo: Repo) -> None:
    await show(target, texts.ASK_MASTER, kb.masters_kb(await repo.masters()))


async def view_days(target: CallbackQuery, cfg: Config, note: str = texts.ASK_DAY) -> None:
    today = cfg.now().date()
    days = bookable_days(today, cfg.days_ahead, cfg.closed_weekdays)
    await show(target, note, kb.days_kb(days, today))


async def view_slots(target: Message | CallbackQuery, data: dict, cfg: Config, repo: Repo,
                     note: str | None = None) -> None:
    service = await repo.service(data["service_id"])
    day = date.fromisoformat(data["day"])
    slots = await repo.free_slots(service, data["master_id"] or None, day)
    if not slots:
        today = cfg.now().date()
        days = bookable_days(today, cfg.days_ahead, cfg.closed_weekdays)
        await show(target, texts.NO_SLOTS.format(day=texts.fmt_day(day, today)), kb.days_kb(days, today))
        return
    header = note or f"🕐 Free time on <b>{texts.fmt_day(day, cfg.now().date())}</b>:"
    await show(target, header, kb.slots_kb(slots))


async def _data_or_restart(cb: CallbackQuery, state: FSMContext, repo: Repo, *keys: str) -> dict | None:
    """Returns saved choices, or restarts the flow if the bot was restarted meanwhile."""
    data = await state.get_data()
    if all(k in data for k in keys):
        return data
    await cb.answer(texts.SESSION_EXPIRED)
    await view_services(cb, state, repo)
    return None


async def _master_name(repo: Repo, master_id: int) -> str:
    if not master_id:
        return "Any available master"
    m = await repo.master(master_id)
    return m.name if m else "—"


# ---------- entry points ----------
@router.message(F.text == texts.BTN_BOOK)
@router.message(Command("book"))
async def start_booking(message: Message, state: FSMContext, repo: Repo) -> None:
    await view_services(message, state, repo)


@router.callback_query(kb.NavCb.filter(F.to == "book"))
async def start_booking_cb(cb: CallbackQuery, state: FSMContext, repo: Repo) -> None:
    await view_services(cb, state, repo)


# ---------- choices ----------
@router.callback_query(kb.SvcCb.filter())
async def chose_service(cb: CallbackQuery, callback_data: kb.SvcCb, state: FSMContext, repo: Repo) -> None:
    await state.set_state(Book.flow)
    await state.set_data({"service_id": callback_data.id})
    await view_masters(cb, repo)


@router.callback_query(kb.MasterCb.filter())
async def chose_master(cb: CallbackQuery, callback_data: kb.MasterCb, state: FSMContext,
                       repo: Repo, cfg: Config) -> None:
    if await _data_or_restart(cb, state, repo, "service_id") is None:
        return
    await state.update_data(master_id=callback_data.id)
    await view_days(cb, cfg)


@router.callback_query(kb.DayCb.filter())
async def chose_day(cb: CallbackQuery, callback_data: kb.DayCb, state: FSMContext,
                    repo: Repo, cfg: Config) -> None:
    if await _data_or_restart(cb, state, repo, "service_id", "master_id") is None:
        return
    day = datetime.strptime(callback_data.d, "%Y%m%d").date()
    data = await state.update_data(day=day.isoformat())
    await view_slots(cb, data, cfg, repo)


@router.callback_query(kb.TimeCb.filter())
async def chose_time(cb: CallbackQuery, callback_data: kb.TimeCb, state: FSMContext,
                     repo: Repo, cfg: Config) -> None:
    data = await _data_or_restart(cb, state, repo, "service_id", "master_id", "day")
    if data is None:
        return
    start = datetime.combine(date.fromisoformat(data["day"]), datetime.strptime(callback_data.t, "%H%M").time())
    await state.update_data(start=start.isoformat())
    service = await repo.service(data["service_id"])
    text = texts.summary(service, await _master_name(repo, data["master_id"]), start, cfg.now().date())
    await show(cb, text, kb.confirm_kb())


# ---------- navigation ----------
@router.callback_query(kb.NavCb.filter(F.to.in_({"services", "masters", "days", "slots"})))
async def go_back(cb: CallbackQuery, callback_data: kb.NavCb, state: FSMContext,
                  repo: Repo, cfg: Config) -> None:
    to = callback_data.to
    if to == "services":
        await view_services(cb, state, repo)
    elif to == "masters":
        if await _data_or_restart(cb, state, repo, "service_id") is not None:
            await view_masters(cb, repo)
    elif to == "days":
        if await _data_or_restart(cb, state, repo, "service_id", "master_id") is not None:
            await view_days(cb, cfg)
    else:
        data = await _data_or_restart(cb, state, repo, "service_id", "master_id", "day")
        if data is not None:
            await view_slots(cb, data, cfg, repo)


@router.callback_query(kb.NavCb.filter(F.to == "abort"))
async def abort(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(cb, texts.ABORTED)


# ---------- confirm & phone ----------
@router.callback_query(kb.NavCb.filter(F.to == "confirm"))
async def confirm(cb: CallbackQuery, state: FSMContext, repo: Repo, cfg: Config, bot: Bot) -> None:
    data = await _data_or_restart(cb, state, repo, "service_id", "master_id", "day", "start")
    if data is None:
        return
    user = await repo.get_user(cb.from_user.id)
    if user and user.phone:
        await cb.answer()
        if isinstance(cb.message, Message):
            await cb.message.edit_reply_markup(reply_markup=None)
            await finalize(cb.message, cb.from_user.id, state, repo, cfg, bot)
        return
    await state.set_state(Book.phone)
    await cb.answer()
    if isinstance(cb.message, Message):
        await cb.message.edit_reply_markup(reply_markup=None)
    await bot.send_message(cb.from_user.id, texts.ASK_PHONE, reply_markup=kb.phone_request())


@router.message(Book.phone, F.contact)
async def got_phone(message: Message, state: FSMContext, repo: Repo, cfg: Config, bot: Bot) -> None:
    if message.contact and message.from_user:
        await repo.set_phone(message.from_user.id, message.contact.phone_number)
        await finalize(message, message.from_user.id, state, repo, cfg, bot)


@router.message(Book.phone, F.text == texts.BTN_SKIP)
async def skip_phone(message: Message, state: FSMContext, repo: Repo, cfg: Config, bot: Bot) -> None:
    if message.from_user:
        await finalize(message, message.from_user.id, state, repo, cfg, bot)


@router.message(Book.phone)
async def phone_other(message: Message) -> None:
    await message.answer(texts.ASK_PHONE, reply_markup=kb.phone_request())


async def finalize(message: Message, user_id: int, state: FSMContext, repo: Repo, cfg: Config, bot: Bot) -> None:
    data = await state.get_data()
    start = datetime.fromisoformat(data["start"])
    booking = await repo.create_booking(user_id, data["service_id"], data["master_id"] or None, start)
    if booking is None:
        await state.set_state(Book.flow)
        await message.answer(texts.SLOT_TAKEN, reply_markup=kb.main_menu())
        await view_slots(message, data, cfg, repo)
        return

    await state.clear()
    today = cfg.now().date()
    await message.answer(texts.booked(booking, today, cfg.address), reply_markup=kb.main_menu())

    owner_text = texts.owner_new_booking(booking, today)
    for admin_id in cfg.admin_ids:
        await safe_send(bot, admin_id, owner_text)
    if cfg.demo_mode and user_id not in cfg.admin_ids:
        await safe_send(bot, user_id, "👀 <i>Demo: this is the message the owner receives:</i>\n\n" + owner_text)
