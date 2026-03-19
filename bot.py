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

from telegram import BotCommand
from config import BOT_TOKEN
from database import init_db, track_message

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
    "ебал", "ебло", "ёблан", "ебанат", "мудак", "мудила",
    "мудачок", "пидор", "пидорас", "пиздюк", "залупа", "шлюха",
    "шлюшка", "бля", "нахуй", "похуй", "похуйку", "ёпт", "ёпта",
    "заебал", "заебала", "заебали", "заебись", "заёб",
    "пиздить", "пиздит", "отъебись", "отъебите",
    "выёбываться", "выёбывается",
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

    # Нормализуем: lowercase + ё → е
    text = (update.message.text or "").lower().replace("ё", "е")
    words = set(re.findall(r'\w+', text, re.UNICODE))
    swear_count = len(words & _SWEAR_NORMALIZED)

    track_message(user.id, user.username, user.first_name, swear_count)

    logger.info("MSG from %s (@%s): %r | swears=%d", user.first_name, user.username, update.message.text, swear_count)

    if swear_count and random.random() < 0.25:
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

    async def set_commands(app):
        await app.bot.set_my_commands([
            BotCommand("help",     "📖 Помощь по командам"),
            BotCommand("top",      "📊 Статистика чата"),
            BotCommand("dice",     "🎲 Бросить кубик"),
            BotCommand("coinflip", "🪙 Орёл или решка"),
            BotCommand("king",     "👑 Выбрать короля дня"),
            BotCommand("roast",    "🔥 Опалить кого-нибудь"),
            BotCommand("rate",     "⭐ Оценить фото"),
            BotCommand("weather",  "🌤 Погода"),
        ])
        logger.info("Команды обновлены")

    app.post_init = set_commands

    logger.info("Бот запущен")
    app.run_polling(poll_interval=0, drop_pending_updates=True)


if __name__ == "__main__":
    main()
