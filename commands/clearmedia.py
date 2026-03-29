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
        failed = 0
        if os.path.isdir(PHOTOS_DIR):
            for fname in os.listdir(PHOTOS_DIR):
                fpath = os.path.join(PHOTOS_DIR, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                        deleted += 1
                    except OSError as file_err:
                        failed += 1
                        logger.warning("clearmedia: не удалось удалить %s: %s", fpath, file_err)

        msg = f"🗑 Галерея очищена.\nУдалено файлов с диска: {deleted}"
        if failed:
            msg += f"\n⚠️ Не удалось удалить: {failed}"
        await update.message.reply_text(msg)
        logger.info("clearmedia: выполнено владельцем %s, файлов удалено: %d", user.id, deleted)
    except Exception as e:
        logger.error("clearmedia error: %s", e)
        await update.message.reply_text(f"❌ Ошибка при очистке: {e}")
