# ==============================================================================
# commands/stats.py — Команда /stats: личная статистика пользователя
# ==============================================================================

import html
from telegram import Update
from telegram.ext import ContextTypes
from database import get_user_stats


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stats — личная статистика. В ответ на сообщение — статистика того пользователя."""
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    else:
        target = update.effective_user

    if target.is_bot:
        await update.message.reply_text("У ботов нет статистики 🤖")
        return

    chat_id = update.effective_chat.id
    s = get_user_stats(target.id, chat_id)

    name = html.escape(target.first_name or "User")
    lines = [f"📊 <b>Статистика {name}</b>\n"]

    # Активность
    rank_str = f"  <i>(#{s['msg_rank']} в чате)</i>" if s["msg_count"] else ""
    lines.append(f"💬 Сообщений: <b>{s['msg_count']}</b>{rank_str}")
    lines.append(f"🤬 Матов замечено: <b>{s['swear_count']}</b>")

    if s["king_count"]:
        lines.append(f"👑 Король дня: <b>{s['king_count']}</b> раз(а)")

    # Рейтинг
    lines.append("")
    if s["photo_count"]:
        lines.append(f"📸 Фото/видео в рейтинге: <b>{s['photo_count']}</b>")
        lines.append(f"⭐ Средняя оценка: <b>{s['avg_score']}</b>  (лучшая: <b>{s['best_score']}</b>)")
        lines.append(f"🗳 Голосов получено: <b>{s['total_votes']}</b>")
    else:
        lines.append("📸 В рейтинге пока не участвовал")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
