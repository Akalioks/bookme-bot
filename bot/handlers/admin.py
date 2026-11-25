"""Owner panel: schedule, cancellations, stats, broadcast, CSV export.

Access: users listed in ADMIN_IDS. In DEMO_MODE anyone can open it, but a
non-admin only sees and manages their own bookings, and broadcasts only to themselves.
"""
import asyncio
import csv
import io
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, TelegramObject

from .. import keyboards as kb
from .. import texts
from ..config import Config
from ..repo import Repo
from ..slots import bookable_days
from .common import safe_send, show

router = Router(name="admin")


class OwnerOnly(Filter):
    async def __call__(self, event: TelegramObject, cfg: Config) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user) and (cfg.demo_mode or cfg.is_admin(user.id))


router.message.filter(OwnerOnly())
router.callback_query.filter(OwnerOnly())


class AdminSt(StatesGroup):
    broadcast = State()


def scope(user_id: int, cfg: Config) -> int | None:
    """None = see everything (real owner); a user id = demo visitor sees only their own data."""
    return None if cfg.is_admin(user_id) else user_id


async def menu_text(user_id: int, repo: Repo, cfg: Config) -> str:
    today = cfg.now().date()
    todays = await repo.bookings_on(today, scope(user_id, cfg))
    text = f"🛠 <b>Owner panel · {escape(cfg.business_name)}</b>\n\nBookings today: <b>{len(todays)}</b>"
    if todays:
        nxt = next((b for b in todays if b.start >= cfg.now()), None)
        if nxt:
            text += f"\nNext: {nxt.start:%H:%M} · {escape(nxt.service.name)} · {escape(nxt.user.full_name)}"
    if scope(user_id, cfg) is not None:
        text += "\n\n🧪 <i>Demo mode: you see only your own bookings.</i>"
    return text


@router.message(Command("admin"))
async def admin_menu(message: Message, state: FSMContext, repo: Repo, cfg: Config) -> None:
    await state.clear()
    if message.from_user:
        await message.answer(await menu_text(message.from_user.id, repo, cfg),
                             reply_markup=kb.admin_menu_kb(cfg.now().date()))


@router.callback_query(kb.AdmCb.filter(F.action == "menu"))
async def admin_menu_cb(cb: CallbackQuery, state: FSMContext, repo: Repo, cfg: Config) -> None:
    await state.clear()
    await show(cb, await menu_text(cb.from_user.id, repo, cfg), kb.admin_menu_kb(cfg.now().date()))


# ---------- schedule ----------
async def schedule_view(user_id: int, d: str, repo: Repo, cfg: Config):
    day = datetime.strptime(d, "%Y%m%d").date()
    bookings = await repo.bookings_on(day, scope(user_id, cfg))
    title = f"📋 <b>Schedule · {texts.fmt_day(day, cfg.now().date())}</b>\n\n"
    if not bookings:
        return title + "No bookings yet.", kb.admin_back_kb()
    lines = []
    for b in bookings:
        phone = f" · {escape(b.user.phone)}" if b.user.phone else ""
        lines.append(f"<b>{b.start:%H:%M}–{b.end:%H:%M}</b> · {b.service.emoji} {escape(b.service.name)} · "
                     f"{escape(b.master.name)}\n     👤 {escape(b.user.full_name)}{phone} · #{b.id}")
    return title + "\n".join(lines) + "\n\nTap a booking below to cancel it.", kb.admin_schedule_kb(bookings, d)


@router.callback_query(kb.AdmCb.filter(F.action == "day"))
async def admin_day(cb: CallbackQuery, callback_data: kb.AdmCb, repo: Repo, cfg: Config) -> None:
    text, markup = await schedule_view(cb.from_user.id, callback_data.d, repo, cfg)
    await show(cb, text, markup)


@router.callback_query(kb.AdmCb.filter(F.action == "pick"))
async def admin_pick(cb: CallbackQuery, cfg: Config) -> None:
    today = cfg.now().date()
    await show(cb, "Choose a day:", kb.admin_days_kb(bookable_days(today, cfg.days_ahead, cfg.closed_weekdays), today))


@router.callback_query(kb.AdmCancelCb.filter())
async def admin_cancel(cb: CallbackQuery, callback_data: kb.AdmCancelCb, repo: Repo, cfg: Config, bot: Bot) -> None:
    b = await repo.cancel(callback_data.id, only_user_id=scope(cb.from_user.id, cfg))
    if b is None:
        await cb.answer("Already cancelled.", show_alert=True)
    else:
        await safe_send(bot, b.user_id,
                        "😔 Sorry, your visit was cancelled by the salon:\n\n"
                        + texts.booking_line(b, cfg.now().date()) + "\n\nPlease choose another time.",
                        reply_markup=kb.book_now_kb())
    text, markup = await schedule_view(cb.from_user.id, callback_data.d, repo, cfg)
    await show(cb, f"✅ Booking #{callback_data.id} cancelled, the client was notified.\n\n" + text, markup)


# ---------- stats ----------
@router.callback_query(kb.AdmCb.filter(F.action == "stats"))
async def admin_stats(cb: CallbackQuery, repo: Repo, cfg: Config) -> None:
    now = cfg.now()
    today = datetime.combine(now.date(), datetime.min.time())
    who = scope(cb.from_user.id, cfg)
    ahead = await repo.stats(today, today + timedelta(days=8), who)
    past = await repo.stats(today - timedelta(days=30), today, who)
    top = "\n".join(f"  • {escape(name)} — {n}" for name, n in past["by_service"][:3]) or "  —"
    text = ("📊 <b>Stats</b>\n\n"
            f"<b>Next 7 days:</b> {ahead['count']} bookings · €{ahead['revenue']} expected\n"
            f"<b>Last 30 days:</b> {past['count']} visits · €{past['revenue']}\n\n"
            f"<b>Top services (30 days):</b>\n{top}")
    await show(cb, text, kb.admin_back_kb())


# ---------- export ----------
@router.callback_query(kb.AdmCb.filter(F.action == "export"))
async def admin_export(cb: CallbackQuery, repo: Repo, cfg: Config, bot: Bot) -> None:
    rows = await repo.all_bookings(scope(cb.from_user.id, cfg))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "date", "start", "end", "service", "price_eur", "master", "client", "username", "phone", "status"])
    for b in rows:
        w.writerow([b.id, f"{b.start:%Y-%m-%d}", f"{b.start:%H:%M}", f"{b.end:%H:%M}", b.service.name,
                    b.service.price, b.master.name, b.user.full_name, b.user.username or "", b.user.phone or "", b.status])
    await cb.answer()
    data = buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens it correctly
    await bot.send_document(cb.from_user.id, BufferedInputFile(data, filename=f"bookings_{cfg.now():%Y%m%d}.csv"),
                            caption=f"📤 {len(rows)} bookings")


# ---------- broadcast ----------
@router.callback_query(kb.AdmCb.filter(F.action == "broadcast"))
async def admin_broadcast(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminSt.broadcast)
    await show(cb, "📢 Send me the message for all clients (e.g. a promo or holiday hours).\n\n/admin — cancel")


@router.message(AdminSt.broadcast, F.text)
async def broadcast_preview(message: Message, state: FSMContext, repo: Repo, cfg: Config) -> None:
    if not message.from_user or (message.text or "").startswith("/"):
        return
    await state.update_data(text=message.html_text)
    who = scope(message.from_user.id, cfg)
    count = 1 if who else len(await repo.all_user_ids())
    note = " (demo: only you)" if who else ""
    await message.answer(f"<b>Preview:</b>\n\n{message.html_text}\n\n— will be sent to {count} user(s){note}.",
                         reply_markup=kb.broadcast_confirm_kb())


@router.callback_query(kb.BcastCb.filter())
async def broadcast_send(cb: CallbackQuery, callback_data: kb.BcastCb, state: FSMContext,
                         repo: Repo, cfg: Config, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    if callback_data.go != "send" or "text" not in data:
        await show(cb, "Broadcast cancelled.", kb.admin_back_kb())
        return
    who = scope(cb.from_user.id, cfg)
    targets = [who] if who else await repo.all_user_ids()
    await show(cb, f"Sending to {len(targets)} user(s)…")
    sent = 0
    for uid in targets:
        sent += await safe_send(bot, uid, data["text"])
        await asyncio.sleep(0.05)  # stay well under Telegram's rate limits
    await show(cb, f"✅ Broadcast sent to {sent} of {len(targets)} user(s).", kb.admin_back_kb())
