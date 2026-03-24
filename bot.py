# ==============================================================================
# bot.py — Главный файл бота
# ==============================================================================

import json
import logging
import os
import re
import random
import time
from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    filters,
)

from telegram import BotCommand, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from config import BOT_TOKEN, PROXY_URL
from database import init_db, track_message

from commands.debug import debug_command
from commands.dice import dice_command
from commands.mge import mge_command
from commands.roast import roast_command
from commands.top import top_command, top_callback
from commands.rate import rate_command, rate_callback, handle_rate_photo, handle_rate_video
from commands.help import help_command
from commands.weather import weather_command, weather_callback
from commands.steam import steam_command, steam_callback
from commands.stats import stats_command
from commands.anon import anon_command, handle_anon_cancel, handle_anon_message
from commands.news import news_command

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
    "дрочи",                                # дрочить...
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
    "Ай-яй-яй, {name}! Что за слова такие!",
    "Полегче на поворотах, {name}!",
    "{name}, рот помой!",
    "Мама слышит тебя, {name}!",
    "Культурнее надо быть, {name}!",
    "Ого, {name}! Такие слова знаешь! 😳",
    "Фильтруй базар, {name}!",
    "Лексикон на уровне, {name}",
    "{name}, это что, норма?",
    "Слушай, {name}, ну зачем так-то?",
    "Словарный запас {name} пополняется не туда",
    "{name} открыл рот и сразу всё стало ясно",
    "Сохраню это для твоего личного дела, {name}",
    "{name}, у тебя всё хорошо? Просто спрашиваю",
]

# Cooldown: последнее время ответа на мат по chat_id
_swear_last_response: dict[int, float] = {}
# Минимальная пауза между ответами на маты (секунды)
_SWEAR_COOLDOWN = 15

# ==============================================================================
# Rate limiter — кулдаун команд на юзера
# ==============================================================================

# Кулдаун по умолчанию (секунды). Отдельные команды можно переопределить.
_DEFAULT_CMD_COOLDOWN = 10

# Переопределения для конкретных команд (0 = без лимита)
_CMD_COOLDOWNS: dict[str, int] = {
    "/help":    30,
    "/start":   0,
    "/debug":   0,
    # Королевские команды не ограничиваем — ими пользуется только король
    "/kfine":   0,
    "/kpardon": 0,
    "/kdecree": 0,
    "/kreward": 0,
    "/ktax":    0,
    # /weather и /steam бьют по внешним API
    "/weather": 30,
    "/steam":   20,
    "/anon":    30,
    # /rate — фото в личке → чат, лимит 5 минут
    "/rate":    300,
}

# Словарь: (user_id, command) → timestamp последнего разрешённого вызова
_cmd_last_used: dict[tuple[int, str], float] = {}


async def _rate_limit_guard(update, context):
    """Middleware (group=-1): удаляет спам-команды молча."""
    msg = update.message
    if not msg or not msg.text or not msg.text.startswith("/"):
        return

    user = update.effective_user
    if not user or user.is_bot:
        return

    # Нормализуем "/mge@botname" → "/mge"
    command = msg.text.split()[0].split("@")[0].lower()
    cooldown = _CMD_COOLDOWNS.get(command, _DEFAULT_CMD_COOLDOWN)

    if cooldown == 0:
        return  # без лимита — пропускаем

    key = (user.id, command)
    now = time.time()
    last = _cmd_last_used.get(key, 0)

    if now - last < cooldown:
        # Спам — удаляем сообщение и останавливаем обработку
        try:
            await msg.delete()
        except Exception:
            pass
        raise ApplicationHandlerStop

    # Первый / разрешённый вызов — фиксируем время
    _cmd_last_used[key] = now


# ==============================================================================
# Setup guard — бот требует /start и права на удаление сообщений
# ==============================================================================

_SETUP_FILE = os.path.join(os.path.dirname(__file__), "setup_chats.json")

def _load_setup_chats() -> set[int]:
    try:
        with open(_SETUP_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def _save_setup_chats() -> None:
    with open(_SETUP_FILE, "w", encoding="utf-8") as f:
        json.dump(list(_setup_chats), f)

_setup_chats: set[int] = _load_setup_chats()


async def _setup_guard(update, context):
    """Middleware (group=-1): блокирует команды в не-инициализированных группах."""
    msg = update.message
    if not msg or not msg.text:
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return

    # /start пропускаем всегда — через него происходит инициализация
    command = msg.text.split()[0].split("@")[0].lower()
    if command == "/start":
        return

    if chat.id not in _setup_chats:
        await msg.reply_text("Сосунок, папочка пока не работает! Пропишите /start")
        raise ApplicationHandlerStop


async def _group_start_command(update, context):
    """Инициализация бота в группе через /start."""
    chat = update.effective_chat

    # Уже инициализирован — тихо удаляем команду
    if chat.id in _setup_chats:
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    # Проверяем, есть ли у бота право удалять сообщения
    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    can_delete = getattr(bot_member, "can_delete_messages", False)

    if not can_delete:
        await update.message.reply_text(
            "Вы что тупые? Папочка сказал: дайте права на удаление сообщений! "
            "Выдайте — и снова пропишите /start"
        )
        return

    _setup_chats.add(chat.id)
    _save_setup_chats()
    await update.message.reply_text(
        "Молодец сынок, папочка начинает работать"
    )


async def _send_swear_response(context) -> None:
    """Job: отправляет ответ на мат после дебаунс-паузы."""
    d = context.job.data
    chat_id = d["chat_id"]

    # Проверяем глобальный cooldown для чата
    last = _swear_last_response.get(chat_id, 0)
    if time.time() - last < _SWEAR_COOLDOWN:
        return

    _swear_last_response[chat_id] = time.time()

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=random.choice(SWEAR_RESPONSES).format(name=d["name"]),
            reply_to_message_id=d["message_id"],
        )
    except Exception:
        pass


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

    if swear_count and update.effective_chat.type != "private":
        name = user.first_name or user.username or "дружок"

        # Дебаунсинг: отменяем предыдущий отложенный ответ для этого чата
        for job in context.job_queue.get_jobs_by_name(f"swear_{chat_id}"):
            job.schedule_removal()

        # Случайно решаем отвечать ли (50%) — но с учётом cooldown в _send_swear_response
        if random.random() < 0.45:
            context.job_queue.run_once(
                _send_swear_response,
                2.5,  # 2.5 сек задержка — ждём пока закончат спамить
                data={
                    "chat_id": chat_id,
                    "name": name,
                    "message_id": update.message.message_id,
                },
                name=f"swear_{chat_id}",
            )


def _save_chat_id_to_config(new_id: int) -> None:
    """Перезаписывает строку CHAT_ID в config.py."""
    config_path = os.path.join(os.path.dirname(__file__), "config.py")
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r"^CHAT_ID\s*=.*$", f"CHAT_ID = {new_id}", content, flags=re.MULTILINE)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)


async def _on_bot_added(update, context):
    """Срабатывает когда бот добавлен в группу — сохраняет CHAT_ID."""
    event = update.my_chat_member
    new_status = event.new_chat_member.status
    chat = event.chat

    if new_status not in ("member", "administrator"):
        return
    if chat.type not in ("group", "supergroup"):
        return

    import config
    chat_id = chat.id
    config.CHAT_ID = chat_id
    _save_chat_id_to_config(chat_id)

    logger.info("Бот добавлен в группу %r, CHAT_ID обновлён на %s", chat.title, chat_id)

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Привет сосунки!\n\n"
                "Чтобы батя начал работать:\n"
                "1. Выдайте мне права на <b>удаление сообщений</b>\n"
                "2. Пропишите /start\n\n"
                "Пока не сделаете — ни одна команда работать не будет!"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def app_command(update, context):
    """Открывает Mini App с Steam скидками и галереей рейтингов."""
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🚀 Открыть приложение",
            web_app=WebAppInfo(url="https://144.31.75.246.sslip.io"),
        )
    ]])
    await update.message.reply_text("Скидки Steam и галерея рейтингов:", reply_markup=kb)


async def gallery_command(update, context):
    """Отвечает на сообщение с кнопкой открытия галереи в браузере."""
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🖼 Галерея", url="https://144.31.75.246.sslip.io")
    ]])
    reply_to = update.message.reply_to_message
    if reply_to:
        await reply_to.reply_text("🖼 Галерея рейтингов:", reply_markup=kb)
    else:
        await update.message.reply_text("🖼 Галерея рейтингов:", reply_markup=kb)


async def _private_command_guard(update, context):
    """Отвечает на неизвестные команды в личке."""
    await update.message.reply_text(
        "❌ В личке доступны только:\n"
        "/rate — отправить фото на оценку группы\n"
        "/help — список команд группы"
    )


def main():
    init_db()

    builder = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
    )
    if PROXY_URL:
        builder = builder.request(HTTPXRequest(proxy=PROXY_URL, read_timeout=15, write_timeout=15, connect_timeout=10))
        logger.info("Используется прокси: %s", PROXY_URL)
    else:
        builder = builder.request(HTTPXRequest(read_timeout=15, write_timeout=15, connect_timeout=10))
    app = builder.build()

    # Middleware (group=-1): сначала rate limiter, потом setup guard
    app.add_handler(
        MessageHandler(filters.COMMAND, _rate_limit_guard),
        group=-1,
    )
    app.add_handler(
        MessageHandler(filters.COMMAND & filters.ChatType.GROUPS, _setup_guard),
        group=-1,
    )

    # /start в группе — инициализация бота
    app.add_handler(CommandHandler("start", _group_start_command, filters=filters.ChatType.GROUPS))

    # В личке работают только /start, /help, /rate
    app.add_handler(CommandHandler("start",    help_command,    filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("help",     help_command))
    app.add_handler(CommandHandler("rate",     rate_command,    filters=filters.ChatType.PRIVATE))

    # Команды только для групп
    app.add_handler(CommandHandler("debug",   debug_command,   filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("dice",    dice_command,    filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("roast",   roast_command,   filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("top",     top_command,     filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("weather", weather_command, filters=filters.ChatType.GROUPS))

    # MGE
    app.add_handler(CommandHandler("mge",   mge_command,   filters=filters.ChatType.GROUPS))

    # Steam скидки
    app.add_handler(CommandHandler("steam", steam_command, filters=filters.ChatType.GROUPS))

    # Личная статистика
    app.add_handler(CommandHandler("stats", stats_command, filters=filters.ChatType.GROUPS))

    # Анонимные сообщения в группу
    app.add_handler(CommandHandler("anon",   anon_command,   filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("cancel", handle_anon_cancel, filters=filters.ChatType.PRIVATE))

    # Новости от владельца (только личка)
    app.add_handler(CommandHandler("news",  news_command,  filters=filters.ChatType.PRIVATE))

    # Mini App
    app.add_handler(CommandHandler("app",     app_command,     filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("gallery", gallery_command, filters=filters.ChatType.GROUPS))

    # Ловим любые другие команды в личке и вежливо отказываем
    app.add_handler(MessageHandler(
        filters.COMMAND & filters.ChatType.PRIVATE,
        _private_command_guard,
    ))

    # Неизвестные команды в группе
    async def _unknown_command(update, context):
        await update.message.reply_text("Сосунок я таких слов не знаю!")

    app.add_handler(MessageHandler(
        filters.COMMAND & filters.ChatType.GROUPS,
        _unknown_command,
    ))

    # Автоопределение CHAT_ID при добавлении бота в группу
    app.add_handler(ChatMemberHandler(_on_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))

    # Приём фото/видео в личке для /rate
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE,
        handle_rate_photo,
    ))
    app.add_handler(MessageHandler(
        filters.VIDEO & filters.ChatType.PRIVATE,
        handle_rate_video,
    ))

    # Inline-кнопки
    app.add_handler(CallbackQueryHandler(top_callback,     pattern=r"^top_"))
    app.add_handler(CallbackQueryHandler(rate_callback,    pattern=r"^(anon_|rate_)"))
    app.add_handler(CallbackQueryHandler(weather_callback, pattern=r"^w(forecast|refresh):"))
    app.add_handler(CallbackQueryHandler(steam_callback,   pattern=r"^steam"))

    # Анонимные сообщения в личке + трекинг в группах
    async def _maybe_token_reply(update, context):
        if update.effective_chat and update.effective_chat.type == "private":
            await handle_anon_message(update, context)
        else:
            await _track_message(update, context)

    # Трекинг текстовых сообщений (без команд)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _maybe_token_reply))

    async def set_commands(app):
        from telegram import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeDefault

        group_commands = [
            BotCommand("help",    "Помощь по командам"),
            BotCommand("top",     "Статистика чата"),
            BotCommand("dice",    "Бросить кубик"),
            BotCommand("roast",   "Подколоть участника"),
            BotCommand("weather", "Погода"),
            BotCommand("mge",     "Фраза из МГЕ"),
            BotCommand("steam",   "Топ скидок в Steam"),
            BotCommand("app",     "Открыть мини-приложение"),
            BotCommand("gallery", "Галерея рейтингов"),
            BotCommand("stats",   "Личная статистика"),
            BotCommand("anon",    "Анонимное сообщение в группу"),
        ]

        private_commands = [
            BotCommand("rate",  "Отправить фото на оценку группы"),
            BotCommand("help",  "Список команд группы"),
            BotCommand("news",  "Написать в группу от бота"),
        ]

        # Для дефолтного scope — пустой список (не показываем /start нигде)
        await app.bot.set_my_commands([], scope=BotCommandScopeDefault())
        await app.bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
        await app.bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
        logger.info("Команды обновлены для всех scope-ов")

    app.post_init = set_commands

    logger.info("Бот запущен")
    app.run_polling(poll_interval=0, drop_pending_updates=True)


if __name__ == "__main__":
    main()
