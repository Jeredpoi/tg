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
from telegram.request import HTTPXRequest
from config import BOT_TOKEN, PROXY_URL
from database import init_db, track_message

from commands.debug import debug_command
from commands.dice import dice_command
from commands.king import king_command, kfine_command, kpardon_command, kdecree_command
from commands.roast import roast_command
from commands.top import top_command, top_callback
from commands.rate import rate_command, rate_callback, handle_rate_photo
from commands.help import help_command
from commands.coinflip import coinflip_command
from commands.weather import weather_command

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Точные слова (ё → е нормализуется при сравнении)
SWEAR_WORDS = {
    "блять", "блядь", "блядина", "сука", "сучка", "пизда", "пиздец",
    "пиздёж", "хуй", "хуйня", "хуета", "ебать", "ёбаный", "ёб", "еби",
    "ебал", "ебло", "ёблан", "ебанат", "мудак", "мудила",
    "мудачок", "пидор", "пидорас", "пиздюк", "залупа", "шлюха",
    "шлюшка", "бля", "нахуй", "похуй", "похуйку", "ёпт", "ёпта",
    "заебал", "заебала", "заебали", "заебись", "заёб",
    "пиздить", "пиздит", "отъебись", "отъебите",
    "выёбываться", "выёбывается",
    "долбоёб", "долбоёбина", "дебил", "дебилизм",
    "ублюдок", "чмо", "уёбок", "уёбище",
}
_SWEAR_NORMALIZED = {w.replace("ё", "е") for w in SWEAR_WORDS}

# Корни — если корень встречается внутри любого слова, считается матом
# Покрывают все словоформы: ебал/ебут/наебал/выебал и т.д.
_SWEAR_ROOTS = [
    "еба", "еби", "ебё", "ебу", "ебл",   # ебать и все формы
    "ёба", "ёби", "ёбл",
    "пизд",                                 # пизда, пиздец, пиздить...
    "бляд",                                 # блядь, блядина...
    "хуй", "хуе", "хуя", "хую",           # хуй и все падежи
    "залуп",                                # залупа...
    "пидар", "пидор",                       # все формы
    "мудак", "мудил",                       # мудак, мудила...
    "дрочи", "дрочи",                       # дрочить...
]
_SWEAR_ROOTS = [r.replace("ё", "е") for r in _SWEAR_ROOTS]


def _count_swears(text: str) -> int:
    """Считает количество матерных слов с учётом корней."""
    normalized = text.lower().replace("ё", "е")
    words = re.findall(r'\w+', normalized, re.UNICODE)
    count = 0
    for word in words:
        if word in _SWEAR_NORMALIZED:
            count += 1
        elif any(root in word for root in _SWEAR_ROOTS):
            count += 1
    return count

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
    """Считает сообщения и маты всех участников (раздельно по чатам)."""
    if not update.message:
        return
    user = update.effective_user
    if not user or user.is_bot:
        return

    chat_id = update.effective_chat.id

    text = update.message.text or ""
    swear_count = _count_swears(text)

    track_message(user.id, user.username, user.first_name, swear_count, chat_id)

    logger.info(
        "MSG [chat=%s] from %s (@%s): %r | swears=%d",
        chat_id, user.first_name, user.username, update.message.text, swear_count,
    )

    if swear_count and random.random() < 0.25:
        name = user.first_name or user.username or "дружок"
        await update.message.reply_text(
            random.choice(SWEAR_RESPONSES).format(name=name)
        )


def main():
    init_db()

    builder = ApplicationBuilder().token(BOT_TOKEN)
    if PROXY_URL:
        builder = builder.request(HTTPXRequest(proxy=PROXY_URL))
        logger.info("Используется прокси: %s", PROXY_URL)
    app = builder.build()

    # Обычные команды
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

    # Королевские команды (доступны всем, но внутри проверяется — ты ли король)
    app.add_handler(CommandHandler("kfine",   kfine_command))
    app.add_handler(CommandHandler("kpardon", kpardon_command))
    app.add_handler(CommandHandler("kdecree", kdecree_command))

    # Приём фото в личке для /rate
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE,
        handle_rate_photo,
    ))

    # Inline-кнопки
    app.add_handler(CallbackQueryHandler(top_callback,  pattern=r"^top_"))
    app.add_handler(CallbackQueryHandler(rate_callback, pattern=r"^(anon_|rate_)"))

    # Трекинг текстовых сообщений (без команд)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _track_message))

    async def set_commands(app):
        from telegram import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeDefault

        commands = [
            BotCommand("help",     "📖 Помощь по командам"),
            BotCommand("top",      "📊 Статистика чата"),
            BotCommand("dice",     "🎲 Бросить кубик"),
            BotCommand("coinflip", "🪙 Орёл или решка"),
            BotCommand("king",     "👑 Выбрать короля дня"),
            BotCommand("roast",    "🔥 Опалить кого-нибудь"),
            BotCommand("rate",     "⭐ Оценить фото (личка)"),
            BotCommand("weather",  "🌤 Погода"),
            BotCommand("kfine",    "⚖️ [Король] Оштрафовать"),
            BotCommand("kpardon",  "🕊️ [Король] Помиловать"),
            BotCommand("kdecree",  "📜 [Король] Издать указ"),
        ]

        # Обновляем команды для всех scope-ов, чтобы перезаписать старые (в т.ч. установленные через BotFather)
        await app.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        await app.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
        await app.bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())
        logger.info("Команды обновлены для всех scope-ов")

    app.post_init = set_commands

    logger.info("Бот запущен")
    app.run_polling(poll_interval=0, drop_pending_updates=True)


if __name__ == "__main__":
    main()
