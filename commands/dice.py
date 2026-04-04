# ==============================================================================
# commands/dice.py — Команда /dice
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes
from chat_config import get_setting


async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /dice.
    Отправляет стандартный Telegram-кубик 🎲.
    """
    msg = await update.message.reply_dice(emoji="🎲")

    try:
        await update.message.delete()
    except Exception:
        pass

    delay = get_setting("autodel_dice")
    if delay:
        _cid, _mid = update.effective_chat.id, msg.message_id

        async def _del_dice(ctx):
            try:
                await ctx.bot.delete_message(_cid, _mid)
            except Exception:
                pass

        context.job_queue.run_once(_del_dice, delay)
