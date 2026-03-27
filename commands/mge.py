# ==============================================================================
# commands/mge.py — /mge: рандомная фраза из серии МГЕ
# ==============================================================================

import html
import random
from telegram import Update
from telegram.ext import ContextTypes
from config import MGE_PHRASES
from database import track_bot_message


async def mge_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /mge [или ответом на сообщение] — отправляет случайную фразу из МГЕ.
    Если команда является ответом на чьё-то сообщение, упоминает этого пользователя.
    """
    speaker, phrase = random.choice(MGE_PHRASES)

    reply = update.message.reply_to_message
    if reply and reply.from_user and not reply.from_user.is_bot:
        target = reply.from_user
        mention = f"@{target.username}" if target.username else html.escape(target.first_name)
        text = f"{mention}\n\n🎭 <b>{speaker}:</b>\n«{phrase}»"
    else:
        text = f"🎭 <b>{speaker}:</b>\n«{phrase}»"

    msg = await update.message.reply_text(text, parse_mode="HTML")
    track_bot_message(update.effective_chat.id, msg.message_id, f"🎭 {speaker}: «{phrase[:40]}»")
