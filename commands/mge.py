# ==============================================================================
# commands/mge.py — /mge: рандомная фраза из серии МГЕ
# ==============================================================================

import random
from telegram import Update
from telegram.ext import ContextTypes
from config import MGE_PHRASES


async def mge_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /mge [или ответом на сообщение] — отправляет случайную фразу из МГЕ.
    Если команда является ответом на чьё-то сообщение, упоминает этого пользователя.
    """
    speaker, phrase = random.choice(MGE_PHRASES)

    reply = update.message.reply_to_message
    if reply and reply.from_user and not reply.from_user.is_bot:
        target = reply.from_user
        mention = f"@{target.username}" if target.username else target.first_name
        text = f"{mention}\n\n🎭 *{speaker}:*\n«{phrase}»"
    else:
        text = f"🎭 *{speaker}:*\n«{phrase}»"

    await update.message.reply_text(text, parse_mode="Markdown")
