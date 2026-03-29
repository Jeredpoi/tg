# ==============================================================================
# commands/dice.py — Команда /dice
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes
from commands.utils import autodel


async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /dice. Отправляет стандартный Telegram-кубик 🎲."""
    msg = await update.message.reply_dice(emoji="🎲")
    await autodel(context, "autodel_dice", update.effective_chat.id,
                  update.message.message_id, msg.message_id)
