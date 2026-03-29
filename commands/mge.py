# ==============================================================================
# commands/mge.py — /mge: рандомная фраза из серии МГЕ
# ==============================================================================

import html
import random
from telegram import Update
from telegram.ext import ContextTypes
from config import MGE_PHRASES
from chat_config import get_custom_mge_phrases
from database import track_bot_message


async def mge_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /mge [или ответом на сообщение] — отправляет случайную фразу из МГЕ.
    Если команда является ответом на чьё-то сообщение, упоминает этого пользователя.
    """
    # Объединяем стандартные и кастомные фразы
    custom = [(p["char"], p["phrase"]) for p in get_custom_mge_phrases()]
    all_phrases = MGE_PHRASES + custom
    speaker, phrase = random.choice(all_phrases)

    reply = update.message.reply_to_message
    safe_speaker = html.escape(speaker)
    safe_phrase  = html.escape(phrase)

    if reply and reply.from_user and not reply.from_user.is_bot:
        target = reply.from_user
        mention = f"@{target.username}" if target.username else html.escape(target.first_name)
        text = f"{mention}\n\n🎭 <b>{safe_speaker}:</b>\n«{safe_phrase}»"
    else:
        text = f"🎭 <b>{safe_speaker}:</b>\n«{safe_phrase}»"

    msg = await update.message.reply_text(text, parse_mode="HTML")
    track_bot_message(update.effective_chat.id, msg.message_id, f"🎭 {speaker}: «{phrase[:40]}»")
