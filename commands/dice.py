# ==============================================================================
# commands/dice.py — Команда /dice
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes


async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /dice.
    Отправляет стандартный Telegram-кубик 🎲.
    """
    await update.message.reply_dice(emoji="🎲")
