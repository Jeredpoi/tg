# ==============================================================================
# commands/stats.py — Команда /stats: личная статистика пользователя
# ==============================================================================

import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import get_user_stats, get_streak, get_user_achievements
from commands.achievements import ACHIEVEMENTS, CAT_EASY, CAT_HARD, CAT_SECRET
from chat_config import get_setting


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

    # Ачивка «Любопытный» — тому, кто вызвал команду (не цели)
    requester = update.effective_user
    if requester and not requester.is_bot:
        _uid, _name = requester.id, requester.first_name or requester.username or "Участник"

        async def _check_stats_ach(ctx):
            from commands.achievements import check_simple_achievements
            await check_simple_achievements(ctx.bot, chat_id, _uid, _name, "stats_check")

        context.job_queue.run_once(_check_stats_ach, 1)
    s = get_user_stats(target.id, chat_id)

    name = html.escape(target.first_name or "User")
    lines = [f"📊 <b>Статистика {name}</b>\n"]

    # Активность
    rank_str = f"  <i>(#{s['msg_rank']} в чате)</i>" if s["msg_count"] else ""
    lines.append(f"💬 Сообщений: <b>{s['msg_count']}</b>{rank_str}")
    lines.append(f"🤬 Матов замечено: <b>{s['swear_count']}</b>")

    if s["king_count"]:
        lines.append(f"👑 Король дня: <b>{s['king_count']}</b> раз(а)")

    # Стрик активности
    streak, max_streak = get_streak(target.id, chat_id)
    if streak or max_streak:
        streak_line = f"🔥 Стрик: <b>{streak}</b> дн."
        if max_streak > streak:
            streak_line += f"  (рекорд: {max_streak} дн.)"
        lines.append(streak_line)

    # Рейтинг
    lines.append("")
    if s["photo_count"]:
        lines.append(f"📸 Фото/видео в рейтинге: <b>{s['photo_count']}</b>")
        lines.append(f"⭐ Средняя оценка: <b>{s['avg_score']}</b>  (лучшая: <b>{s['best_score']}</b>)")
        lines.append(f"🗳 Голосов получено: <b>{s['total_votes']}</b>")
    else:
        lines.append("📸 В рейтинге пока не участвовал")

    # Краткий итог ачивок
    rows = get_user_achievements(target.id, chat_id)
    earned_ids = {r["achievement_id"] for r in rows if r["achievement_id"] in ACHIEVEMENTS}
    total_ach  = len(ACHIEVEMENTS)
    earned_ach = len(earned_ids)
    secrets_earned = sum(1 for aid in earned_ids if ACHIEVEMENTS[aid].get("secret"))
    secrets_total  = sum(1 for a in ACHIEVEMENTS.values() if a.get("secret"))

    lines.append("")
    if earned_ach:
        lines.append(
            f"🏆 Ачивок: <b>{earned_ach}/{total_ach}</b> "
            f"<i>(секретных: {secrets_earned}/{secrets_total})</i>"
        )
    else:
        lines.append("🏆 Ачивок пока нет")

    # Кнопка «Ачивки» — открывает список ачивок для кликнувшего в этом чате
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏆 Мои ачивки", callback_data=f"ach:{chat_id}:easy:0"),
    ]])

    msg = await update.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)

    try:
        await update.message.delete()
    except Exception:
        pass

    delay = get_setting("autodel_stats")
    if delay:
        _cid, _mid = update.effective_chat.id, msg.message_id

        async def _del_stats(ctx):
            try:
                await ctx.bot.delete_message(_cid, _mid)
            except Exception:
                pass

        context.job_queue.run_once(_del_stats, delay)
