# ==============================================================================
# commands/help.py — Команда /help
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes

HELP_TEXT = """
🤖 <b>Команды бота</b>

🎲 <b>Развлечения</b>
/dice — бросить кубик
/coinflip — орёл или решка
/roast @user — подколоть участника
/king — выбрать короля чата дня
/8ball <i>вопрос</i> — магический шар (скоро)

📊 <b>Статистика</b>
/top — топ активности и матов

📸 <b>Фото</b>
/rate — оценить фото (ответь на фото)

🌤 <b>Погода</b>
/weather <i>город</i> — узнать погоду

🛠 <b>Прочее</b>
/debug — информация о чате и пользователе
/help — это сообщение
""".strip()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команд /help и /start."""
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")
