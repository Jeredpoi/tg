# ==============================================================================
# bot.py — Главный файл бота
# ==============================================================================

import logging
import random
import re
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import BOT_TOKEN
from database import init_db, upsert_user, increment_message, increment_swear

from commands.debug import debug_command
from commands.dice import dice_command
from commands.king import king_command
from commands.roast import roast_command
from commands.top import top_command, top_callback
from commands.rate import rate_command, rate_callback
from commands.help import help_command
from commands.coinflip import coinflip_command
from commands.weather import weather_command

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Список мат-слов (добавляй по необходимости)
SWEAR_WORDS = {
    "блять", "блядь", "блядина", "сука", "сучка", "пизда", "пиздец",
    "пиздёж", "хуй", "хуйня", "хуета", "ебать", "ёбаный", "ёб", "еби",
    "ебал", "ебло", "ёблан", "ебанат", "ебаный", "мудак", "мудила",
    "мудачок", "пидор", "пидорас", "пиздюк", "залупа", "шлюха",
    "шлюшка", "ёбаный", "ёб твою мать", "бля", "нахуй", "похуй",
    "похуй", "похуйку", "ёпт", "ёпта", "заебал", "заебала", "заебали",
    "заебись", "заёб", "пиздить", "пиздит", "пиздит", "пизда",
    "отъебись", "отъебите", "выёбываться", "выёбывается",
    "долбоёб", "долбоёбина", "идиот", "дебил", "дебилизм",
    "тупица", "ублюдок", "скотина", "чмо", "уёбок", "уёбище",
}

# Нормализованный список (ё → е) для сравнения
_SWEAR_NORMALIZED = {w.replace("ё", "е") for w in SWEAR_WORDS}

SWEAR_RESPONSES = [
    "Ай-яй-яй, {name}! Что за слова такие! 😤",
    "Полегче на поворотах, {name}! 🤨",
    "{name}, рот помой! 🧼",
    "Мама слышит тебя, {name}! 😱",
    "Культурнее надо быть, {name}! 📚",
    "Ого, {name}! Такие слова знаешь! 😳",
    "Фильтруй базар, {name}! 🫡",
]


async def _track_message(update, context):
    """Считает сообщения и маты всех участников."""
    user = update.effective_user
    if not user or user.is_bot:
        return

    upsert_user(user.id, user.username, user.first_name)
    increment_message(user.id)

    # Проверяем наличие мат-слов (нормализуем ё → е, убираем пунктуацию)
    text = (update.message.text or "").lower().replace("ё", "е")
    words = set(re.findall(r'\w+', text, re.UNICODE))
    count = len(words & _SWEAR_NORMALIZED)
    if count:
        increment_swear(user.id, count)
        # С вероятностью ~25% отвечаем на мат
        if random.random() < 0.25:
            name = user.first_name or user.username or "дружок"
            await update.message.reply_text(
                random.choice(SWEAR_RESPONSES).format(name=name)
            )


def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start",    help_command))
    app.add_handler(CommandHandler("help",     help_command))
    app.add_handler(CommandHandler("debug",    debug_command))
    app.add_handler(CommandHandler("dice",     dice_command))
    app.add_handler(CommandHandler("king",     king_command))
    app.add_handler(CommandHandler("roast",    roast_command))
    app.add_handler(CommandHandler("top",      top_command))
    app.add_handler(CommandHandler("rate",     rate_command))
    app.add_handler(CommandHandler("coinflip", coinflip_command))
    app.add_handler(CommandHandler("weather",  weather_command))

    # Inline-кнопки
    app.add_handler(CallbackQueryHandler(top_callback,  pattern=r"^top_"))
    app.add_handler(CallbackQueryHandler(rate_callback, pattern=r"^(anon_|rate_)"))

    # Трекинг сообщений (без команд)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _track_message))

    logger.info("Бот запущен")
    app.run_polling(poll_interval=0, drop_pending_updates=True)


if __name__ == "__main__":
    main()
