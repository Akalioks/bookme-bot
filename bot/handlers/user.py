"""Start, About, My bookings, cancelling a booking."""
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import texts
from ..config import Config
from ..repo import Repo
from .common import safe_send, show

router = Router(name="user")

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@router.message(CommandStart())
@router.message(Command("help"))
async def start(message: Message, state: FSMContext, repo: Repo, cfg: Config) -> None:
    await state.clear()
    u = message.from_user
    if u:
        await repo.ensure_user(u.id, u.full_name, u.username)
    await message.answer(texts.welcome(u.first_name if u else "there", cfg.business_name, cfg.demo_mode),
                         reply_markup=kb.main_menu())


@router.message(F.text == texts.BTN_ABOUT)
@router.message(Command("about"))
async def about(message: Message, cfg: Config) -> None:
    hours = f"{cfg.open_time:%H:%M}–{cfg.close_time:%H:%M}"
    closed = ", ".join(WEEKDAY_NAMES[d] for d in sorted(cfg.closed_weekdays))
    await message.answer(texts.about(cfg.business_name, cfg.address, cfg.phone, hours, closed))


async def _my_bookings_view(user_id: int, repo: Repo, cfg: Config):
    bookings = await repo.upcoming_for_user(user_id)
    if not bookings:
        return texts.NO_BOOKINGS, kb.book_now_kb()
    today = cfg.now().date()
    body = "\n\n".join(texts.booking_line(b, today) for b in bookings)
    return f"🗓 <b>Your upcoming visits</b>\n\n{body}", kb.my_bookings_kb(bookings)


@router.message(F.text == texts.BTN_MY)
@router.message(Command("my"))
async def my_bookings(message: Message, repo: Repo, cfg: Config) -> None:
    if message.from_user:
        text, markup = await _my_bookings_view(message.from_user.id, repo, cfg)
        await message.answer(text, reply_markup=markup)


@router.callback_query(kb.MyCancelCb.filter())
async def cancel_booking(cb: CallbackQuery, callback_data: kb.MyCancelCb, repo: Repo, cfg: Config, bot: Bot) -> None:
    user_id = cb.from_user.id
    booking = await repo.booking(callback_data.id)
    if booking is None or booking.user_id != user_id or booking.status != "active":
        await cb.answer("This booking is no longer active.", show_alert=True)
        return
    today = cfg.now().date()

    if callback_data.step == "ask":
        await show(cb, "Cancel this visit?\n\n" + texts.booking_line(booking, today),
                   kb.cancel_confirm_kb(booking.id))
    elif callback_data.step == "no":
        text, markup = await _my_bookings_view(user_id, repo, cfg)
        await show(cb, text, markup)
    else:
        cancelled = await repo.cancel(booking.id, only_user_id=user_id)
        if cancelled is None:
            await cb.answer("This booking is no longer active.", show_alert=True)
            return
        await show(cb, "🗑 Your booking was cancelled.\n\n" + texts.booking_line(booking, today), kb.book_now_kb())
        note = f"🚫 <b>Booking #{booking.id} cancelled by the client</b>\n\n" + texts.booking_line(booking, today)
        for admin_id in cfg.admin_ids:
            await safe_send(bot, admin_id, note)
