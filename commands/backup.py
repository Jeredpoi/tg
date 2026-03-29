# ==============================================================================
# commands/backup.py — /backup: отправить резервную копию БД владельцу
# ==============================================================================

import datetime
import os
from telegram import Update
from telegram.ext import ContextTypes
from config import OWNER_ID, DATABASE_PATH


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/backup — отправить файл базы данных в личку (только владелец, только PM)."""
    if update.effective_user.id != OWNER_ID:
        return

    if update.effective_chat.type != "private":
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    if not os.path.exists(DATABASE_PATH):
        await update.message.reply_text("❌ Файл базы данных не найден.")
        return

    size = os.path.getsize(DATABASE_PATH)
    size_str = f"{size / 1024:.1f} КБ" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} МБ"

    msg = await update.message.reply_text("⏳ Формирую резервную копию...")

    try:
        _msk = datetime.timezone(datetime.timedelta(hours=3))
        now = datetime.datetime.now(_msk)
        filename = f"backup_{now.strftime('%Y-%m-%d_%H-%M')}.db"
        with open(DATABASE_PATH, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=filename,
                caption=(
                    f"🗄 <b>Резервная копия базы данных</b>\n\n"
                    f"📅 {now.strftime('%d.%m.%Y %H:%M')} МСК\n"
                    f"📦 Размер: {size_str}"
                ),
                parse_mode="HTML",
            )
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Не удалось отправить: {e}")
