# ==============================================================================
# commands/clearmedia.py — /clearmedia: очистка всех фото/видео (только владелец)
# ==============================================================================

import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from database import clear_all_photos
from config import OWNER_ID

logger = logging.getLogger(__name__)
PHOTOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "photos"))


async def clearmedia_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or user.id != OWNER_ID:
        await update.message.reply_text("🚫 Эта команда только для владельца бота.")
        return

    try:
        clear_all_photos()

        deleted = 0
        if os.path.isdir(PHOTOS_DIR):
            for fname in os.listdir(PHOTOS_DIR):
                fpath = os.path.join(PHOTOS_DIR, fname)
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    deleted += 1

        await update.message.reply_text(
            f"🗑 Галерея очищена.\n"
            f"Удалено файлов с диска: {deleted}"
        )
        logger.info("clearmedia: выполнено владельцем %s, файлов удалено: %d", user.id, deleted)
    except Exception as e:
        logger.error("clearmedia error: %s", e)
        await update.message.reply_text(f"❌ Ошибка при очистке: {e}")
