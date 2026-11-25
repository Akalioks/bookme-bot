"""Small helpers shared by handlers."""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

log = logging.getLogger(__name__)


async def show(target: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Answers a message, or edits the message whose button was pressed."""
    if isinstance(target, CallbackQuery):
        await target.answer()
        msg = target.message
        if isinstance(msg, Message):
            try:
                await msg.edit_text(text, reply_markup=markup)
                return
            except TelegramBadRequest:  # too old to edit, or nothing changed
                pass
        if target.from_user:
            await target.bot.send_message(target.from_user.id, text, reply_markup=markup)  # type: ignore[union-attr]
        return
    await target.answer(text, reply_markup=markup)


async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    """Sends a message, ignoring users who blocked the bot."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramAPIError as e:
        log.warning("Could not message %s: %s", chat_id, e)
        return False
