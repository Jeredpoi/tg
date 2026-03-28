# ==============================================================================
# commands/help.py — Команда /help + /ownerhelp
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes
from config import OWNER_ID
from chat_config import get_setting

HELP_TEXT = """
🤖 <b>Команды бота</b>

🎲 <b>Развлечения</b>
/dice — бросить кубик
/roast @user — подколоть участника (или ответом на сообщение)
/mge — случайная фраза из МГЕ (можно ответом на сообщение)

📊 <b>Статистика</b>
/top — топ активности, матов и рейтинга /rate
/stats — личная статистика (или ответом — чужая)

📸 <b>Медиа</b>
/rate — отправить фото или видео на оценку группы (в личке боту)
/gallery — открыть галерею фото и видео

🌤 <b>Погода</b>
/weather <i>город</i> — погода + прогноз на 4 дня (без города — повторяет последний)

🎭 <b>Анонимка</b>
/anon — отправить анонимное сообщение в группу (бот спросит в личке)

<b>Прочее</b>
/help — это сообщение
""".strip()

OWNER_HELP_TEXT = """
👑 <b>Команды владельца</b>

⚙️ <b>Управление ботом</b>
/settings — панель настроек бота (только в личке)
/delmsg — удалить сообщения бота из истории (только в личке)
/resend — отправить сообщение от имени бота в группу (только в личке)
/clearmedia — очистить все фото/видео из галереи
/exportstats — выгрузить всю статистику в ZIP (CSV-файлы, только в личке)

🛠 <b>Диагностика</b>
/debug — статус систем, чат-ID, права бота

━━━━━━━━━━━━━━━━━━━━━━━
👥 <b>Публичные команды</b>

🎲 /dice · /roast · /mge
📊 /top · /stats
📸 /rate · /gallery
🌤 /weather
🎭 /anon
❓ /help
""".strip()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команд /help и /start. Автоудаляется если autodel_help > 0."""
    user_msg = update.message
    bot_msg  = await user_msg.reply_text(HELP_TEXT, parse_mode="HTML")

    delay = get_setting("autodel_help")
    if delay:
        chat_id  = user_msg.chat_id
        user_mid = user_msg.message_id
        bot_mid  = bot_msg.message_id

        async def _delete(ctx):
            for mid in [user_mid, bot_mid]:
                try:
                    await ctx.bot.delete_message(chat_id, mid)
                except Exception:
                    pass

        context.job_queue.run_once(_delete, delay)


async def ownerhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ownerhelp — список всех команд для владельца."""
    if update.effective_user.id != OWNER_ID:
        return
    user_msg = update.message
    bot_msg  = await user_msg.reply_text(OWNER_HELP_TEXT, parse_mode="HTML")

    delay = get_setting("autodel_ownerhelp")
    if delay:
        chat_id  = user_msg.chat_id
        user_mid = user_msg.message_id
        bot_mid  = bot_msg.message_id

        async def _delete(ctx):
            for mid in [user_mid, bot_mid]:
                try:
                    await ctx.bot.delete_message(chat_id, mid)
                except Exception:
                    pass

        context.job_queue.run_once(_delete, delay)
