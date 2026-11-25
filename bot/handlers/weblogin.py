"""Logging in to the web admin panel through the Telegram app.

The panel shows a link t.me/<bot>?start=login_<token>. The person taps it, Telegram opens this chat,
the bot asks "Log in?" and the browser logs in by itself after "Confirm". No phone number or password."""
import re
from html import escape

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..repo import Repo
from .common import show

router = Router(name="weblogin")
TOKEN_RE = re.compile(r"^login_([A-Za-z0-9_-]{20,58})$")

ASK = ("🔐 <b>Log in to the admin panel?</b>\n\n"
       "Browser: {browser}\n\n"
       "Confirm only if you are logging in yourself right now. Never confirm a link someone sent you.")
DONE = "✅ <b>You're logged in.</b> Go back to the browser, the panel opens by itself."
DENIED = "❌ Login cancelled. Nobody was let in."
EXPIRED = "⌛ This login link has expired. Refresh the login page and try again."


class WebLoginCb(CallbackData, prefix="wl"):
    token: str
    ok: bool


def ask_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Confirm", callback_data=WebLoginCb(token=token, ok=True).pack()),
        InlineKeyboardButton(text="Cancel", callback_data=WebLoginCb(token=token, ok=False).pack()),
    ]])


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("login_")))
async def login_link(m: Message, command: CommandObject, repo: Repo) -> None:
    match = TOKEN_RE.match(command.args or "")
    row = await repo.web_login(match.group(1)) if match else None
    if row is None:
        await m.answer(EXPIRED)
        return
    await m.answer(ASK.format(browser=escape(row.browser or "unknown")), reply_markup=ask_kb(row.token))


@router.callback_query(WebLoginCb.filter())
async def login_answer(cq: CallbackQuery, callback_data: WebLoginCb, repo: Repo) -> None:
    u = cq.from_user
    ok = await repo.answer_web_login(callback_data.token, callback_data.ok, u.id, u.first_name, u.last_name, u.username)
    await show(cq, (DONE if callback_data.ok else DENIED) if ok else EXPIRED)
