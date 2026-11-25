"""Run with:  python -m bot"""
import asyncio
import contextlib
import logging
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .app import build_dispatcher
from .config import load_config
from .reminders import reminder_loop
from .repo import Repo, seed_demo_data


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    if not cfg.bot_token:
        sys.exit("BOT_TOKEN is empty. Copy .env.example to .env and paste the token from @BotFather.")

    repo = await Repo.create(cfg)
    await seed_demo_data(repo)

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.set_my_commands([
        BotCommand(command="start", description="Main menu"),
        BotCommand(command="book", description="Book an appointment"),
        BotCommand(command="my", description="My bookings"),
        BotCommand(command="about", description="Address & opening hours"),
    ])
    dp = build_dispatcher(cfg, repo)
    reminders = asyncio.create_task(reminder_loop(bot, repo, cfg))
    try:
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reminders
        await repo.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
