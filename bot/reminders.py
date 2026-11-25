"""Background task: sends 24h and 2h reminders. State lives in the DB, so restarts are safe."""
import asyncio
import logging

from aiogram import Bot

from . import keyboards as kb
from . import texts
from .config import Config
from .handlers.common import safe_send
from .repo import Repo

log = logging.getLogger(__name__)


async def send_due_reminders(bot: Bot, repo: Repo, cfg: Config) -> int:
    sent = 0
    for booking, kind in await repo.due_reminders():
        ok = await safe_send(bot, booking.user_id, texts.reminder(booking, kind, cfg.address, cfg.now().date()),
                             reply_markup=kb.reminder_kb(booking.id))
        sent += ok
        await repo.mark_reminded(booking.id, kind)  # mark even if blocked, so we don't retry forever
    return sent


async def reminder_loop(bot: Bot, repo: Repo, cfg: Config, every_sec: int = 60) -> None:
    while True:
        try:
            n = await send_due_reminders(bot, repo, cfg)
            if n:
                log.info("Sent %d reminder(s)", n)
        except Exception:
            log.exception("Reminder loop error")
        await asyncio.sleep(every_sec)
