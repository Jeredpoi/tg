# ==============================================================================
# commands/restart.py — /restart: перезапустить бота (только владелец)
# ==============================================================================

import asyncio
import os
import sys
from telegram import Update
from telegram.ext import ContextTypes
from config import OWNER_ID


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/restart — мягкий перезапуск бота (только владелец, только PM)."""
    if update.effective_user.id != OWNER_ID:
        return

    if update.effective_chat.type != "private":
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    await update.message.reply_text(
        "🔄 <b>Перезапускаю бота...</b>\n\n"
        "<i>Бот будет недоступен несколько секунд.</i>",
        parse_mode="HTML",
    )
    await asyncio.sleep(0.5)
    os.execl(sys.executable, sys.executable, *sys.argv)
