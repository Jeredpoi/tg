# ==============================================================================
# bot.py — Главный файл бота
# ==============================================================================

import json
import logging
import os
import re
import random
import time
import datetime
import urllib.parse
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
from config import (BOT_TOKEN, PROXY_URL, WEBAPP_URL,
                    SWEAR_COOLDOWN, DEFAULT_CMD_COOLDOWN,
                    SWEAR_RESPONSE_DELAY, SWEAR_RESPONSE_CHANCE)

from database import (init_db, track_message, track_daily_swear, get_daily_swear_report,
                       get_best_photo_since, get_and_delete_old_photos)

from commands.debug import debug_command
from commands.dice import dice_command
from commands.mge import mge_command
from commands.roast import roast_command
from commands.top import top_command, top_callback
from commands.rate import rate_command, rate_callback, handle_rate_photo, handle_rate_video
from commands.help import help_command
from commands.weather import weather_command, weather_callback
from commands.stats import stats_command
from commands.anon import anon_command, handle_anon_cancel, handle_anon_message
from commands.clearmedia import clearmedia_command


logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Точные слова (ё → е нормализуется при сравнении)
SWEAR_WORDS = {
    # блядь и формы
    "блять", "блядь", "блядина", "блядский", "блядство",
    # сука и формы
    "сука", "сучка", "сучара", "сученок", "сучий",
    # пизда и формы
    "пизда", "пиздец", "пиздёж", "пиздюк", "пиздатый", "пиздато",
    "пиздить", "пиздит",
    # хуй и формы
    "хуй", "хуйня", "хуета", "нахуй", "похуй", "похуйку",
    # ебать и формы
    "ебать", "ёбаный", "ёб", "еби", "ебал", "ебло", "ёблан",
    "ебанат", "заебал", "заебала", "заебали", "заебись", "заёб",
    "отъебись", "отъебите", "выёбываться", "выёбывается",
    # мудак и формы
    "мудак", "мудила", "мудачок",
    # пидор и формы
    "пидор", "пидорас", "пидрила",
    # залупа
    "залупа",
    # шлюха
    "шлюха", "шлюшка",
    # мягкие
    "бля", "ёпт", "ёпта",
    # долбоёб
    "долбоёб", "долбоёбина",
    # дебил
    "дебил", "дебилизм", "дебильный",
    # другие
    "ублюдок", "чмо", "уёбок", "уёбище", "урод",
    # говно и формы
    "говно", "говнюк", "говняный", "говнистый", "говнище",
    # жопа и формы
    "жопа", "жопой", "жопу", "жопный",
    # срань
    "срань", "срать", "засрать", "насрать",
    # мразь, тварь
    "мразь", "мразота",
    # ёбаный в рот (составные)
    "еблан", "ёблан",
}
_SWEAR_NORMALIZED = {w.replace("ё", "е") for w in SWEAR_WORDS}

# Корни — если корень встречается внутри любого слова, считается матом
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
    "говн",                                 # говно, говнюк...
    "жоп",                                  # жопа и формы
    "сран", "срат",                         # срань, срать...
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
_SWEAR_COOLDOWN = SWEAR_COOLDOWN

# ==============================================================================
# Rate limiter — кулдаун команд на юзера
# ==============================================================================

# Кулдаун по умолчанию (секунды). Отдельные команды можно переопределить.
_DEFAULT_CMD_COOLDOWN = DEFAULT_CMD_COOLDOWN

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
    "/weather": 30,
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

    # Считаем команду как сообщение пользователя в группе
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        track_message(user.id, user.username, user.first_name, 0, chat.id)


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

    if swear_count and update.effective_chat.type in ("group", "supergroup"):
        track_daily_swear(chat_id, user.id, user.first_name or user.username or "Аноним", swear_count)

    if swear_count and update.effective_chat.type != "private":
        name = user.first_name or user.username or "дружок"

        # Дебаунсинг: отменяем предыдущий отложенный ответ для этого чата
        for job in context.job_queue.get_jobs_by_name(f"swear_{chat_id}"):
            job.schedule_removal()

        # Случайно решаем отвечать ли (50%) — но с учётом cooldown в _send_swear_response
        if random.random() < SWEAR_RESPONSE_CHANCE:
            context.job_queue.run_once(
                _send_swear_response,
                SWEAR_RESPONSE_DELAY,
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
    new_content, count = re.subn(r"^CHAT_ID\s*=.*$", f"CHAT_ID = {new_id}", content, flags=re.MULTILINE)
    if count == 0:
        logger.warning("_save_chat_id_to_config: строка CHAT_ID не найдена в config.py — ID не сохранится после перезапуска")
        return
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)


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


async def gallery_command(update, context):
    """Отвечает на сообщение с кнопкой открытия галереи в браузере."""
    user = update.effective_user
    chat = update.effective_chat
    uname = urllib.parse.quote(user.username or user.first_name, safe='')
    url = f"{WEBAPP_URL}?uid={user.id}&uname={uname}&chat_id={chat.id}"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🖼 Галерея", url=url)
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


_MIDNIGHT_MSGS = [
    "За сегодня вы насматерились <b>{total}</b> раз. Какие же вы мелочные 🤡",
    "Итог дня: <b>{total}</b> матерных слов. Культурный чат, ничего не скажешь 👏",
    "Папочка посчитал: <b>{total}</b> матов за день. Вы этим гордитесь? 😐",
    "Дневной рекорд по матам: <b>{total}</b>. Молодцы, сосунки 🏆",
    "Сегодня вы произнесли <b>{total}</b> матерных слов. Мама была бы в шоке 😳",
]

_MEDALS = ["🥇", "🥈", "🥉"]


_MIDNIGHT_ZERO_MSGS = [
    "За сегодня никто не матерился. Гордитесь собой, сосунки 🥲",
    "Чистый день — ни одного мата. Это было неожиданно 😶",
    "Сегодня культурные. Завтра всё равно сорвётесь 🫡",
]

async def _midnight_swear_report(context) -> None:
    """Job: в 00:00 МСК отправляет отчёт по матам за прошедший день."""
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    # Отправляем во все известные чаты + CHAT_ID если задан
    import config as cfg
    target_chats = set(_setup_chats)
    if cfg.CHAT_ID:
        target_chats.add(cfg.CHAT_ID)
    for chat_id in target_chats:
        try:
            total, rows = get_daily_swear_report(chat_id, yesterday)
            if total == 0:
                text = random.choice(_MIDNIGHT_ZERO_MSGS)
            else:
                header = random.choice(_MIDNIGHT_MSGS).format(total=total)
                lines = [f"🤬 {header}\n"]
                for i, (name, count) in enumerate(rows[:5]):
                    medal = _MEDALS[i] if i < 3 else f"{i + 1}."
                    lines.append(f"{medal} {name} — {count} раз(а)")
                text = "\n".join(lines)
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.warning("midnight_swear_report chat=%s: %s", chat_id, e)


async def _private_start(update, context):
    """/start в личке — с поддержкой deep link для галереи (gallery_{chat_id})."""
    if context.args and context.args[0].startswith("gallery_"):
        try:
            chat_id = int(context.args[0][8:])
        except ValueError:
            await help_command(update, context)
            return
        user = update.effective_user
        uname = urllib.parse.quote(user.username or user.first_name, safe='')
        url = f"{WEBAPP_URL}?uid={user.id}&uname={uname}&chat_id={chat_id}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Открыть галерею", url=url)]])
        await update.message.reply_text(
            "🖼 <b>Галерея рейтингов</b>\n\n"
            "Твоя персональная ссылка — имя будет отображаться в комментариях:",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return
    await help_command(update, context)


async def _weekly_best_photo(context) -> None:
    """Каждый понедельник в 00:00 МСК постит лучшее фото за неделю."""
    import config as cfg
    for chat_id in list(_setup_chats):
        try:
            row = get_best_photo_since(days=7, chat_id=chat_id)
            if not row:
                continue
            votes = row["vote_count"]
            avg   = round(row["avg_score"], 1)
            author = "Аноним" if row["anonymous"] else (row["author_name"] or "Аноним")
            photo_id  = row["photo_id"]
            media_type = row["media_type"] or "photo"
            uname_q   = urllib.parse.quote("Скаут", safe="")
            gallery_url = f"{WEBAPP_URL}?chat_id={chat_id}&uname={uname_q}"
            caption = (
                f"🏆 <b>Лучшее фото недели!</b>\n\n"
                f"👤 Автор: {author}\n"
                f"⭐ Средняя оценка: {avg} ({votes} голос(ов))"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Галерея", url=gallery_url)]])
            if media_type == "video":
                await context.bot.send_video(chat_id=chat_id, video=photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                await context.bot.send_photo(chat_id=chat_id, photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            logger.info("weekly_best_photo: отправлено в чат %s", chat_id)
        except Exception as e:
            logger.warning("weekly_best_photo chat=%s: %s", chat_id, e)


async def _cleanup_old_photos(context) -> None:
    """Ежедневно в 03:00 МСК удаляет фото/видео старше 30 дней с диска и из БД."""
    photos_dir = os.path.join(os.path.dirname(__file__), "photos")
    deleted_count = 0
    try:
        old = get_and_delete_old_photos(days=30)
        for key, media_type in old:
            ext = "mp4" if media_type == "video" else "jpg"
            fpath = os.path.join(photos_dir, f"{key}.{ext}")
            if os.path.exists(fpath):
                os.remove(fpath)
                deleted_count += 1
        if deleted_count:
            logger.info("cleanup_old_photos: удалено %d файлов", deleted_count)
    except Exception as e:
        logger.error("cleanup_old_photos: %s", e)


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
    app.add_handler(CommandHandler("start",    _private_start,  filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("help",     help_command))
    app.add_handler(CommandHandler("rate",     rate_command,    filters=filters.ChatType.PRIVATE))

    # Команды только для групп
    app.add_handler(CommandHandler("debug",   debug_command))
    app.add_handler(CommandHandler("dice",    dice_command,    filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("roast",   roast_command,   filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("top",     top_command,     filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("weather", weather_command, filters=filters.ChatType.GROUPS))

    # MGE
    app.add_handler(CommandHandler("mge",   mge_command,   filters=filters.ChatType.GROUPS))


    # Личная статистика
    app.add_handler(CommandHandler("stats", stats_command, filters=filters.ChatType.GROUPS))

    # Анонимные сообщения в группу
    app.add_handler(CommandHandler("anon",   anon_command,   filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("cancel", handle_anon_cancel, filters=filters.ChatType.PRIVATE))

    app.add_handler(CommandHandler("gallery",    gallery_command,    filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("clearmedia", clearmedia_command))

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

    # Анонимные сообщения в личке + трекинг в группах
    async def _maybe_token_reply(update, context):
        if update.effective_chat and update.effective_chat.type == "private":
            await handle_anon_message(update, context)
        else:
            await _track_message(update, context)

    # Трекинг текстовых сообщений (без команд)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _maybe_token_reply))

    async def on_startup(app):
        await app.bot.set_my_description("Скаут на связи 🟢")
        await app.bot.set_my_short_description("Скаут на связи 🟢")
        from telegram import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeDefault

        group_commands = [
            BotCommand("help",    "Помощь по командам"),
            BotCommand("top",     "Статистика чата"),
            BotCommand("dice",    "Бросить кубик"),
            BotCommand("roast",   "Подколоть участника"),
            BotCommand("weather", "Погода"),
            BotCommand("mge",     "Фраза из МГЕ"),
            BotCommand("gallery", "Галерея рейтингов"),
            BotCommand("stats",   "Личная статистика"),
            BotCommand("anon",    "Анонимное сообщение в группу"),
        ]

        private_commands = [
            BotCommand("rate",  "Отправить фото на оценку группы"),
            BotCommand("help",  "Список команд группы"),
            BotCommand("debug", "Отладочная информация"),
        ]

        # Для дефолтного scope — пустой список (не показываем /start нигде)
        await app.bot.set_my_commands([], scope=BotCommandScopeDefault())
        await app.bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
        await app.bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
        logger.info("Команды обновлены для всех scope-ов")

        msk = datetime.timezone(datetime.timedelta(hours=3))

        # Ночной отчёт о матах в 00:00 МСК
        midnight = datetime.time(0, 0, 0, tzinfo=msk)
        app.job_queue.run_daily(_midnight_swear_report, time=midnight, name="midnight_swear")
        logger.info("Ночной отчёт запланирован на 00:00 МСК")

        # Лучшее фото недели — каждый понедельник 00:00 МСК
        app.job_queue.run_daily(
            _weekly_best_photo,
            time=midnight,
            days=(0,),          # 0 = понедельник
            name="weekly_best_photo",
        )
        logger.info("Еженедельное лучшее фото запланировано на пн 00:00 МСК")

        # Авточистка файлов старше 30 дней — ежедневно в 03:00 МСК
        three_am = datetime.time(3, 0, 0, tzinfo=msk)
        app.job_queue.run_daily(_cleanup_old_photos, time=three_am, name="cleanup_old_photos")
        logger.info("Авточистка старых фото запланирована на 03:00 МСК")

    async def on_shutdown(app):
        try:
            await app.bot.set_my_description("Скаут недоступен 🔴")
            await app.bot.set_my_short_description("Скаут недоступен 🔴")
        except Exception:
            pass

    app.post_init = on_startup
    app.post_shutdown = on_shutdown

    logger.info("Бот запущен")
    app.run_polling(poll_interval=0, drop_pending_updates=True)


if __name__ == "__main__":
    main()
