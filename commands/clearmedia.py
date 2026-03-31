# ==============================================================================
# commands/clearmedia.py — /clearmedia: очистка всех фото/видео (только владелец)
# ==============================================================================

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import clear_all_photos
from config import OWNER_ID

logger = logging.getLogger(__name__)
PHOTOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "photos"))


def _count_media_files() -> int:
    """Считает количество медиа-файлов в PHOTOS_DIR (не аватары)."""
    if not os.path.isdir(PHOTOS_DIR):
        return 0
    return sum(
        1 for f in os.listdir(PHOTOS_DIR)
        if os.path.isfile(os.path.join(PHOTOS_DIR, f))
        and f.lower().endswith((".jpg", ".mp4"))
    )


async def clearmedia_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or user.id != OWNER_ID:
        await update.message.reply_text("🚫 Эта команда только для владельца бота.")
        return

    count = _count_media_files()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да, удалить всё", callback_data="clearmedia_confirm"),
        InlineKeyboardButton("❌ Отмена",           callback_data="clearmedia_cancel"),
    ]])
    await update.message.reply_text(
        f"⚠️ <b>Подтверждение очистки</b>\n\n"
        f"Будет удалено из галереи:\n"
        f"• все записи из базы данных\n"
        f"• {count} медиа-файлов с диска\n\n"
        f"Это действие <b>необратимо</b>. Продолжить?",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def clearmedia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопок подтверждения /clearmedia."""
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("🚫 Только для владельца.", show_alert=True)
        return

    if query.data == "clearmedia_cancel":
        await query.answer("Отменено.")
        await query.edit_message_text("❌ Очистка отменена.")
        return

    # clearmedia_confirm
    await query.answer("Удаляю...")
    await query.edit_message_text("⏳ Удаляю медиафайлы...")

    try:
        # Сначала удаляем файлы с диска, потом очищаем БД —
        # чтобы при ошибке ФС не потерять записи в БД
        deleted = 0
        failed = 0
        if os.path.isdir(PHOTOS_DIR):
            for fname in os.listdir(PHOTOS_DIR):
                fpath = os.path.join(PHOTOS_DIR, fname)
                if os.path.isfile(fpath) and fname.lower().endswith((".jpg", ".mp4")):
                    try:
                        os.remove(fpath)
                        deleted += 1
                    except OSError as file_err:
                        failed += 1
                        logger.warning("clearmedia: не удалось удалить %s: %s", fpath, file_err)

        if failed:
            await query.edit_message_text(
                f"⚠️ Не удалось удалить {failed} файл(ов). БД не тронута.\n"
                f"Успешно удалено: {deleted}. Проверь права доступа и повтори.",
                parse_mode="HTML",
            )
            return

        clear_all_photos()

        await query.edit_message_text(
            f"🗑 <b>Галерея очищена.</b>\nУдалено файлов с диска: <b>{deleted}</b>",
            parse_mode="HTML",
        )
        logger.info("clearmedia: выполнено владельцем %s, файлов удалено: %d", query.from_user.id, deleted)
    except Exception as e:
        logger.error("clearmedia error: %s", e)
        await query.edit_message_text(f"❌ Ошибка при очистке: {e}")
