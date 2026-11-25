"""A fake Telegram: feeds updates to the dispatcher and records what the bot sends back."""
import itertools
from datetime import datetime

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import EditMessageText, SendDocument, SendMessage
from aiogram.types import (CallbackQuery, Chat, Contact, InlineKeyboardMarkup, Message, Update,
                           User as TgUser)

from bot.app import build_dispatcher
from bot.config import load_config
from bot.handlers import admin, booking, user, weblogin
from bot.repo import Repo, seed_demo_data


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.ids = itertools.count(1000)

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, SendDocument)):
            return Message(message_id=next(self.ids), date=datetime.now(),
                           chat=Chat(id=method.chat_id, type="private"), text=getattr(method, "text", None))
        if isinstance(method, EditMessageText):
            return Message(message_id=method.message_id or 0, date=datetime.now(),
                           chat=Chat(id=method.chat_id or 0, type="private"), text=method.text)
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def close(self):
        pass


class Client:
    """One simulated Telegram user talking to the bot."""

    def __init__(self, env, user_id, name):
        self.env, self.id = env, user_id
        self.user = TgUser(id=user_id, is_bot=False, first_name=name, username=name.lower())

    def _sent_to_me(self):
        return [c for c in self.env.session.calls
                if getattr(c, "chat_id", None) == self.id and isinstance(c, (SendMessage, EditMessageText))]

    @property
    def last_text(self) -> str:
        return self._sent_to_me()[-1].text

    def texts_since(self, n) -> list[str]:
        return [c.text for c in self._sent_to_me()[n:]]

    def mark(self) -> int:
        return len(self._sent_to_me())

    def buttons(self) -> list[str]:
        for c in reversed(self._sent_to_me()):
            if isinstance(c.reply_markup, InlineKeyboardMarkup):
                return [b.text for row in c.reply_markup.inline_keyboard for b in row]
        return []

    async def say(self, text=None, contact=None):
        msg = Message(message_id=next(self.env.ids), date=datetime.now(), chat=Chat(id=self.id, type="private"),
                      from_user=self.user, text=text,
                      contact=Contact(phone_number=contact, first_name="X", user_id=self.id) if contact else None)
        await self.env.dp.feed_update(self.env.bot, Update(update_id=next(self.env.ids), message=msg))

    async def press(self, label_part: str):
        for c in reversed(self._sent_to_me()):
            if isinstance(c.reply_markup, InlineKeyboardMarkup):
                for row in c.reply_markup.inline_keyboard:
                    for b in row:
                        if label_part in b.text:
                            msg = Message(message_id=getattr(c, "message_id", None) or 1, date=datetime.now(),
                                          chat=Chat(id=self.id, type="private"), text=c.text)
                            cq = CallbackQuery(id=str(next(self.env.ids)), from_user=self.user, chat_instance="ci",
                                               data=b.callback_data, message=msg)
                            await self.env.dp.feed_update(self.env.bot, Update(update_id=next(self.env.ids), callback_query=cq))
                            return
                raise AssertionError(f"No button containing {label_part!r}; have: {self.buttons()}")
        raise AssertionError("No inline keyboard was sent")


class Env:
    def __init__(self, cfg, repo, session):
        self.cfg, self.repo, self.session = cfg, repo, session
        self.ids = itertools.count(1)
        self.bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        for r in (weblogin.router, user.router, admin.router, booking.router):
            r._parent_router = None  # module-level routers can only be attached once; each test gets a fresh dispatcher
        self.dp = build_dispatcher(cfg, repo)

    def client(self, user_id, name):
        return Client(self, user_id, name)


@pytest.fixture
async def make_env(tmp_path):
    repos = []

    async def factory(**overrides):
        settings = {"database_url": f"sqlite+aiosqlite:///{tmp_path}/t{len(repos)}.db",
                    "admin_ids": frozenset(), "demo_mode": True, **overrides}
        cfg = load_config(**settings)
        repo = await Repo.create(cfg)
        await seed_demo_data(repo)
        repos.append(repo)
        return Env(cfg, repo, FakeSession())

    yield factory
    for r in repos:
        await r.close()
