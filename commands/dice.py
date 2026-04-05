# ==============================================================================
# commands/dice.py — Команда /dice
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes
from chat_config import get_setting
from database import increment_user_event


async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /dice.
    Отправляет стандартный Telegram-кубик 🎲.
    """
    msg = await update.message.reply_dice(emoji="🎲")

    user = update.effective_user
    if user and update.effective_chat:
        _uid, _cid = user.id, update.effective_chat.id
        _name = user.first_name or user.username or "Участник"
        _dice_count = increment_user_event(_uid, _cid, "dice")

        async def _check_dice_ach(ctx):
            from commands.achievements import check_simple_achievements
            await check_simple_achievements(ctx.bot, _cid, _uid, _name, "dice_user")
            if _dice_count >= 30:
                await check_simple_achievements(ctx.bot, _cid, _uid, _name, "dice_30")

        context.job_queue.run_once(_check_dice_ach, 1)

    delay = get_setting("autodel_dice")
    if delay:
        try:
            await update.message.delete()
        except Exception:
            pass

        _cid, _mid = update.effective_chat.id, msg.message_id

        async def _del_dice(ctx):
            try:
                await ctx.bot.delete_message(_cid, _mid)
            except Exception:
                pass

        context.job_queue.run_once(_del_dice, delay)
