# ==============================================================================
# commands/exportstats.py — /exportstats: выгрузка статистики в ZIP+CSV (только владелец)
# ==============================================================================

import csv
import datetime
import io
import logging
import zipfile

from telegram import Update
from telegram.ext import ContextTypes

import config
from database import get_connection

logger = logging.getLogger(__name__)


def _make_users_csv(conn) -> str:
    """users.csv — активность участников по всем чатам."""
    rows = conn.execute(
        "SELECT user_id, username, first_name, chat_id, msg_count, swear_count "
        "FROM user_stats ORDER BY chat_id, msg_count DESC"
    ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["user_id", "username", "first_name", "chat_id", "msg_count", "swear_count"])
    for r in rows:
        w.writerow([
            r["user_id"],
            r["username"] or "",
            r["first_name"] or "",
            r["chat_id"],
            r["msg_count"],
            r["swear_count"],
        ])
    return buf.getvalue()


def _make_photos_csv(conn) -> str:
    """photos.csv — рейтинги фото/видео."""
    rows = conn.execute("""
        SELECT key, author_name, anonymous, total_score, vote_count,
               CASE WHEN vote_count > 0
                    THEN ROUND(CAST(total_score AS FLOAT) / vote_count, 2)
                    ELSE 0 END AS avg_score,
               media_type, chat_id, created_at
        FROM photo_ratings
        ORDER BY created_at DESC
    """).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["key", "author", "anonymous", "total_score", "vote_count",
                "avg_score", "media_type", "chat_id", "created_at"])
    for r in rows:
        author = "Анонимно" if r["anonymous"] else (r["author_name"] or "")
        w.writerow([
            r["key"],
            author,
            "да" if r["anonymous"] else "нет",
            r["total_score"],
            r["vote_count"],
            r["avg_score"],
            r["media_type"] or "photo",
            r["chat_id"],
            r["created_at"] or "",
        ])
    return buf.getvalue()


def _make_swears_csv(conn) -> str:
    """daily_swears.csv — история матов по дням и участникам."""
    rows = conn.execute(
        "SELECT chat_id, date, first_name, swear_count "
        "FROM daily_swears ORDER BY date DESC, swear_count DESC"
    ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["chat_id", "date", "first_name", "swear_count"])
    for r in rows:
        w.writerow([r["chat_id"], r["date"], r["first_name"] or "", r["swear_count"]])
    return buf.getvalue()


async def exportstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/exportstats — выгрузить всю статистику в ZIP с CSV-файлами. Только в личке владельца."""
    if update.effective_user.id != config.OWNER_ID:
        return

    try:
        await update.message.delete()
    except Exception:
        pass

    status = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ Формирую статистику...",
    )

    try:
        conn = get_connection()
        try:
            users_csv   = _make_users_csv(conn)
            photos_csv  = _make_photos_csv(conn)
            swears_csv  = _make_swears_csv(conn)

            # Считаем итоги для подписи
            total_users  = conn.execute("SELECT COUNT(*) FROM user_stats").fetchone()[0]
            total_photos = conn.execute("SELECT COUNT(*) FROM photo_ratings").fetchone()[0]
            total_swear_rows = conn.execute("SELECT COUNT(*) FROM daily_swears").fetchone()[0]
        finally:
            conn.close()

        # Собираем ZIP в памяти
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("users.csv",        users_csv.encode("utf-8-sig"))
            zf.writestr("photos.csv",       photos_csv.encode("utf-8-sig"))
            zf.writestr("daily_swears.csv", swears_csv.encode("utf-8-sig"))
        zip_buf.seek(0)

        _msk = datetime.timezone(datetime.timedelta(hours=3))
        today    = datetime.datetime.now(_msk).date().isoformat()
        filename = f"bot_stats_{today}.zip"

        caption = (
            f"📊 <b>Статистика бота</b> на {today} МСК\n\n"
            f"📁 Три файла внутри:\n"
            f"• <code>users.csv</code> — {total_users} записей участников\n"
            f"• <code>photos.csv</code> — {total_photos} фото/видео\n"
            f"• <code>daily_swears.csv</code> — {total_swear_rows} строк истории матов\n\n"
            f"<i>Кодировка UTF-8 с BOM — открывается в Excel без настроек.</i>"
        )

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=zip_buf,
            filename=filename,
            caption=caption,
            parse_mode="HTML",
        )

    except Exception as e:
        logger.exception("exportstats error: %s", e)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Ошибка при формировании статистики: {e}",
        )
    finally:
        try:
            await status.delete()
        except Exception:
            pass
