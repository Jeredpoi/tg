# ==============================================================================
# bot.py — Главный файл бота
# ==============================================================================

import html as _html_mod
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

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from config import (BOT_TOKEN, PROXY_URL, WEBAPP_URL, OWNER_ID,
                    SWEAR_COOLDOWN, DEFAULT_CMD_COOLDOWN,
                    SWEAR_RESPONSE_DELAY, SWEAR_RESPONSE_CHANCE)

from database import (init_db, track_message, track_daily_swear, get_daily_swear_report,
                       get_best_photo_since, get_and_delete_old_photos, track_bot_message)

from commands.debug import debug_command
from commands.dice import dice_command
from commands.mge import mge_command
from commands.roast import roast_command
from commands.top import top_command, top_callback
from commands.rate import rate_command, rate_callback, handle_rate_photo, handle_rate_video, handle_rate_comment
from commands.help import help_command, ownerhelp_command, ownerhelp_pin_callback
from commands.weather import weather_command, weather_callback
from commands.stats import stats_command
from commands.anon import anon_command, handle_anon_cancel, handle_anon_message
from commands.clearmedia import clearmedia_command, clearmedia_callback
from commands.delmsg import delmsg_command, delmsg_callback
from commands.resend import resend_command, handle_resend_message, resend_cancel
from commands.settings import settings_command, settings_callback, handle_settings_input
from commands.exportstats import exportstats_command
from commands.maintenance import is_maintenance, maintenance_command
from commands.backup import backup_command
from commands.setavatar import setavatar_command
from commands.restart import restart_command, send_restart_done
from chat_config import (get_main_chat_id, add_setup_chat, is_setup_chat, get_setting,
                          is_command_enabled, get_custom_swear_responses)


logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Точные слова (ё → е нормализуется при сравнении)
# Только настоящий мат — 4 матерных корня и их производные.
# Вульгарные, но не матерные слова (дебил, урод, говно, жопа, мразь, чмо и т.п.)
# сюда НЕ включаются.
SWEAR_WORDS = {
    # ── блядь и все формы ──────────────────────────────────────────────
    "блядь", "блять", "блядина", "блядский", "блядство",
    "блядовать", "блядун", "бляди", "блядей",

    # ── сука и формы ───────────────────────────────────────────────────
    "сука", "суки", "суке", "суку", "сукой",
    "сучка", "сучки", "сучку", "сучкой",
    "сучара", "сученок", "сучий", "сучьё",

    # ── пизда и все формы ──────────────────────────────────────────────
    "пизда", "пизды", "пизде", "пизду", "пиздой",
    "пиздец", "пиздос",
    "пиздёж", "пиздёжник", "пиздёжница",
    "пиздюк", "пиздюки",
    "пиздатый", "пиздатая", "пиздато", "пиздатее",
    "пиздить", "пиздит", "пиздили", "пиздишь",
    "пизданутый", "пизданутая",
    "пиздануть", "пизданул", "пизданула",
    "распиздяй", "распиздяйство", "распиздяйка",
    "пиздобол", "пиздоболить", "пиздобольство",
    "спиздить", "спиздил", "спиздила", "спиздили",  # украсть
    "отпиздить", "отпиздил", "отпиздила",
    "запиздить", "допиздить",

    # ── хуй и все формы ────────────────────────────────────────────────
    "хуй", "хуя", "хую", "хуем", "хуе",
    "хуйня", "хуйни", "хуйнёй",
    "хуета", "хуйло", "хуила",
    "нахуй", "нахуя",
    "похуй", "похуйку", "похую",
    "нихуя", "нихуёв", "нихуев",
    "дохуя", "дохуев",
    "хуёвый", "хуёвая", "хуёво", "хуёвее", "хуёвость",
    "хуевый", "хуево",
    "хуесос", "хуесоска",
    "хуеплёт", "хуеплет",
    "хуяк",
    "хуярить", "хуяришь", "хуярит", "хуярю", "хуярили",
    "захуярить", "нахуярить", "отхуярить", "похуярить", "схуярить",
    "захуячить", "нахуячить", "схуячить", "отхуячить",
    "хуяра", "схуяли", "схуя",
    "охуеть", "охуел", "охуела", "охуели", "охуею", "охуеешь", "охуеет",
    "охуенный", "охуенно", "охуенная", "охуенные", "охуенного",
    "охуительный", "охуительно", "охуительная", "охуительные",

    # ── ебать и все формы ──────────────────────────────────────────────
    "ебать", "ебёт", "ебут", "ебал", "ебала", "ебали",
    "ёбаный", "ёбаная", "ёбаные", "ёбаному",
    "ёб", "ёбнуть", "ёбнул", "ёбнула", "ёбнулся",
    "ёбнутый", "ёбнутая",
    "еби", "ебло", "ёблан", "еблан",
    "ебанат", "ебанько",
    "заебал", "заебала", "заебали", "заебись",
    "заёб", "заёбывать", "заёбываться", "заёбывается",
    "отъебись", "отъебите", "отъебал",
    "выёбываться", "выёбывается", "выёбон",
    "уёбок", "уёбище", "уёбан",
    "долбоёб", "долбоёбина", "долбоёбизм",
    "наёб", "наёбывать", "наёбать", "наёбал", "наёбала", "наёбали",
    "поёб", "поёбывать",
    "проёб", "проёбать", "проёбал", "проёбала",
    "разъёб", "разъёбывать",
    "переёб", "переёбывать", "переёбывается",
    "подъёбывать", "подъёбка", "подъёб",
    "съёбывать", "съёбал", "съёбалась", "съёбаться",
    "ёбля", "ёбарь",

    # ── мудак и формы ──────────────────────────────────────────────────
    "мудак", "мудаки", "мудаку", "мудаков",
    "мудила", "мудило",
    "мудачок", "мудачка",
    "мудозвон", "мудозвоны",

    # ── пидор и формы ──────────────────────────────────────────────────
    "пидор", "пидора", "пидоры", "пидоров",
    "пидорас", "пидораса",
    "пидрила",
    "пидарас",
    "пидорина",

    # ── залупа ─────────────────────────────────────────────────────────
    "залупа", "залупы", "залупе", "залупу", "залупой",
    "залупаться", "залупается",

    # ── шлюха ──────────────────────────────────────────────────────────
    "шлюха", "шлюхи", "шлюхе", "шлюху", "шлюхой",
    "шлюшка", "шлюшки",

    # ── дрочить ────────────────────────────────────────────────────────
    "дрочить", "дрочит", "дрочил", "дрочила", "дрочили",
    "дрочу", "задрочить", "задрочил", "задрочился",

    # ── восклицания / эвфемизмы ────────────────────────────────────────
    "бля", "ёпт", "ёпта", "ёпте",
}
_SWEAR_NORMALIZED = {w.replace("ё", "е") for w in SWEAR_WORDS}

# Корни — совпадение только в начале слова или после приставки.
# Убраны не-матерные корни: говн, жоп, сран, срат.
_SWEAR_ROOTS_RAW = [
    "еба", "еби", "ебё", "ебу", "ебл", "ебы",   # ебать и все формы
    "ёба", "ёби", "ёбл", "ёбы",
    "пизд",                                # пизда, пиздец, пиздить...
    "бляд",                                # блядь, блядина...
    "хуй", "хуе", "хуя", "хую",          # хуй и все падежи/производные
    "залуп",                               # залупа...
    "пидар", "пидор",                      # все формы
    "мудак", "мудил",                      # мудак, мудила...
    "дроч",                                # дрочить и формы
]
_SWEAR_ROOTS_NORM = [r.replace("ё", "е") for r in _SWEAR_ROOTS_RAW]

# Русские приставки — мат часто идёт после них (за+ебал, о+хуеть, с+пиздить...)
_PREFIXES = (
    "за", "на", "по", "от", "вы", "у", "о", "пере", "раз", "рас",
    "с", "об", "пре", "под", "до", "из", "без", "не", "ни",
    "при", "про", "пред", "въ", "отъ", "объ", "предъ",
)

def _has_swear_root(word: str) -> bool:
    """Проверяет содержит ли слово матерный корень (с учётом приставок)."""
    for root in _SWEAR_ROOTS_NORM:
        if word.startswith(root):
            return True
        for prefix in _PREFIXES:
            if word.startswith(prefix + root):
                return True
    return False


# Таблица замены латинских букв, визуально похожих на кириллицу.
# Только настоящие гомоглифы: e≈е  a≈а  o≈о  c≈с  p≈р  x≈х  y≈у
# НЕ включаем b/h/u/i/k/m/n — не похожи, дают ложные срабатывания на английских словах.
_LAT_TO_CYR = str.maketrans({
    'e': 'е', 'a': 'а', 'o': 'о', 'c': 'с', 'p': 'р', 'x': 'х', 'y': 'у',
    'E': 'Е', 'A': 'А', 'O': 'О', 'C': 'С', 'P': 'Р', 'X': 'Х', 'Y': 'У',
})

# Символы цензуры между буквами (x*й, б.ять).
# Дефис НЕ удаляем — нормальные составные слова (по-русски, тёмно-синий).
_CENSOR_STRIP_RE = re.compile(r'(?<=[а-яёА-ЯЁa-zA-Z])[\*\.]+(?=[а-яёА-ЯЁa-zA-Z])')

# Паттерны цензурированных матов — проверяем ДО удаления символов цензуры,
# чтобы не потерять короткие слова (х*й→хй — 2 буквы, не поймаем через слова).
_CENSORED_RE = re.compile(
    r'х[\*\.][йя]'        # х*й / х.й / х*я
    r'|б[\*\.]ять'        # б*ять
    r'|б[\*\.]ядь'        # б*ядь
    r'|п[\*\.]зда'        # п*зда
    r'|п[\*\.]здец'       # п*здец
    r'|[её][\*\.]ать'     # е*ать / ё*ать
    r'|е[\*\.]б',         # е*б (фрагмент ебать)
    re.IGNORECASE,
)

# Начала слов — ложные срабатывания через prefix+root детектор.
# "себ" = приставка "с" + корень "еб" → "Себастьян", "себялюбие" и т.п.
_SWEAR_FP_STARTS = frozenset(["себ"])


def _count_swears(text: str) -> int:
    """Считает количество матерных слов с учётом корней."""
    if not text:
        return 0
    # Latin→Cyrillic гомоглифы
    mapped = text.translate(_LAT_TO_CYR)
    lower = mapped.lower().replace('ё', 'е')

    # 1) Явные цензурированные паттерны (х*й и т.п.) — до удаления символов
    count = len(_CENSORED_RE.findall(lower))

    # 2) Обычные слова после удаления символов цензуры
    clean = _CENSOR_STRIP_RE.sub('', lower)
    for word in re.findall(r'[а-яё]+', clean):
        if word in _SWEAR_NORMALIZED:
            count += 1
        elif (len(word) >= 4
              and not any(word.startswith(fp) for fp in _SWEAR_FP_STARTS)
              and _has_swear_root(word)):
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


async def _maintenance_guard(update, context):
    """Middleware (group=-3): блокирует все команды не-владельца в режиме обслуживания."""
    if not is_maintenance():
        return
    user = update.effective_user
    if user and user.id == OWNER_ID:
        return
    msg = update.message
    if msg:
        try:
            await msg.delete()
        except Exception:
            pass
        chat = update.effective_chat
        if chat and chat.type in ("group", "supergroup"):
            try:
                note = await context.bot.send_message(
                    chat_id=chat.id,
                    text="🔧 Бот на техническом обслуживании.",
                    disable_notification=True,
                )
                async def _del(ctx):
                    try:
                        await ctx.bot.delete_message(chat.id, note.message_id)
                    except Exception:
                        pass
                context.job_queue.run_once(_del, 5)
            except Exception:
                pass
    raise ApplicationHandlerStop


async def _rate_limit_guard(update, context):
    """Middleware (group=-1): при спаме команд уведомляет пользователя и останавливает обработку."""
    msg = update.message
    if not msg or not msg.text or not msg.text.startswith("/"):
        return

    user = update.effective_user
    if not user or user.is_bot:
        return

    # Нормализуем "/mge@botname" → "/mge"
    command = msg.text.split()[0].split("@")[0].lower()

    # Команда отключена владельцем — тихо удаляем
    if not is_command_enabled(command):
        if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
            try:
                await msg.delete()
            except Exception:
                pass
        raise ApplicationHandlerStop

    cooldown = _CMD_COOLDOWNS.get(command, get_setting("cmd_cooldown"))

    if cooldown == 0:
        return  # без лимита — пропускаем

    key = (user.id, command)
    now = time.time()
    last = _cmd_last_used.get(key, 0)

    if now - last < cooldown:
        remaining = int(cooldown - (now - last)) + 1
        chat = update.effective_chat
        if chat and chat.type in ("group", "supergroup"):
            try:
                await msg.delete()
            except Exception:
                pass
            try:
                note = await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"⏳ <b>{remaining} сек.</b> до следующего использования",
                    parse_mode="HTML",
                    disable_notification=True,
                )
                async def _del_cd(ctx):
                    try:
                        await ctx.bot.delete_message(chat.id, note.message_id)
                    except Exception:
                        pass
                context.job_queue.run_once(_del_cd, 2)
            except Exception:
                pass
        elif chat and chat.type == "private":
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

async def _setup_guard(update, context):
    """Middleware (group=-2): блокирует команды в не-инициализированных группах."""
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

    if not is_setup_chat(chat.id):
        await msg.reply_text("Сосунок, папочка пока не работает! Пропишите /start")
        raise ApplicationHandlerStop


async def _group_start_command(update, context):
    """Инициализация бота в группе через /start."""
    chat = update.effective_chat

    # Уже инициализирован — тихо удаляем команду
    if is_setup_chat(chat.id):
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

    add_setup_chat(chat.id)
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
        all_responses = SWEAR_RESPONSES + get_custom_swear_responses()
        template = random.choice(all_responses)
        try:
            text = template.format(name=d["name"])
        except (KeyError, IndexError):
            # Кастомный ответ с лишними {плейсхолдерами} — подставляем имя вручную
            text = template.replace("{name}", d["name"])
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=d["message_id"],
        )
        track_bot_message(chat_id, msg.message_id, msg.text)
    except Exception as e:
        logger.warning("_send_swear_response: chat=%s err=%s", chat_id, e)


_avatar_cache_set: set[int] = set()   # user_id уже закэшированных за эту сессию
_AVATARS_DIR = os.path.join(os.path.dirname(__file__), "photos", "avatars")
_AVATAR_TTL = 24 * 3600


async def _cache_avatar(context, user_id: int) -> None:
    """Фоновая задача: скачивает и сохраняет аватар пользователя на диск."""
    os.makedirs(_AVATARS_DIR, exist_ok=True)
    cache_path = os.path.join(_AVATARS_DIR, f"{user_id}.jpg")
    # Не обновляем если файл свежий
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) < _AVATAR_TTL:
            return
    try:
        photos = await context.bot.get_user_profile_photos(user_id=user_id, limit=1)
        if not photos.total_count:
            return
        file_obj = await context.bot.get_file(photos.photos[0][-1].file_id)
        await file_obj.download_to_drive(cache_path)
    except Exception:
        pass


async def _track_message(update, context):
    """Считает сообщения и маты всех участников (раздельно по чатам)."""
    if not update.message:
        return
    user = update.effective_user
    if not user or user.is_bot:
        return

    # Кэшируем аватар один раз за сессию (в фоне, не блокируем)
    if user.id not in _avatar_cache_set:
        _avatar_cache_set.add(user.id)
        uid = user.id

        async def _do_cache_avatar(ctx):
            await _cache_avatar(ctx, uid)

        context.job_queue.run_once(
            _do_cache_avatar,
            0,
            name=f"avatar_{uid}",
        )

    chat_id = update.effective_chat.id

    text = update.message.text or update.message.caption or ""
    swear_count = _count_swears(text)

    track_message(user.id, user.username, user.first_name, swear_count, chat_id)

    if swear_count and update.effective_chat.type in ("group", "supergroup"):
        track_daily_swear(chat_id, user.id, user.first_name or user.username or "Аноним", swear_count)

    if swear_count and update.effective_chat.type != "private" and get_setting("swear_detect"):
        name = user.first_name or user.username or "дружок"

        # Дебаунсинг: отменяем предыдущий отложенный ответ для этого чата
        for job in context.job_queue.get_jobs_by_name(f"swear_{chat_id}"):
            job.schedule_removal()

        # Случайно решаем отвечать ли — но с учётом cooldown в _send_swear_response
        if random.random() < get_setting("swear_response_chance"):
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
    """Отправляет кнопку галереи через deep link — без личных данных в группе."""
    chat = update.effective_chat
    bot_username = context.bot.username
    # Ссылка ведёт в личку бота, где он выдаст персональный URL с uid/uname
    deep_url = f"https://t.me/{bot_username}?start=gallery_{chat.id}"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🖼 Открыть галерею", url=deep_url)
    ]])
    reply_to = update.message.reply_to_message
    if reply_to:
        msg = await reply_to.reply_text(
            "🖼 Нажми кнопку — бот пришлёт тебе персональную ссылку в личку:",
            reply_markup=kb,
        )
    else:
        msg = await update.message.reply_text(
            "🖼 Нажми кнопку — бот пришлёт тебе персональную ссылку в личку:",
            reply_markup=kb,
        )
    track_bot_message(chat.id, msg.message_id, "🖼 Галерея рейтингов")


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
    if not get_setting("midnight_report"):
        return
    msk = datetime.timezone(datetime.timedelta(hours=3))
    yesterday = (datetime.datetime.now(msk).date() - datetime.timedelta(days=1)).isoformat()
    # Отправляем только в основную группу
    main_id = get_main_chat_id()
    if not main_id:
        logger.warning("midnight_swear_report: основная группа не назначена (/settings → Чаты бота)")
        return
    target_chats = {main_id}
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
                    lines.append(f"{medal} {_html_mod.escape(name or 'Аноним')} — {count} раз(а)")
                text = "\n".join(lines)
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            track_bot_message(chat_id, msg.message_id, text[:80])
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
        uname = urllib.parse.quote(user.username or user.first_name or str(user.id), safe='')
        url = f"{WEBAPP_URL}?uid={user.id}&uname={uname}&chat_id={chat_id}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Открыть галерею", url=url)]])
        bot_msg = await update.message.reply_text(
            "🖼 <b>Галерея рейтингов</b>\n\n"
            "Твоя персональная ссылка — имя будет отображаться в комментариях:",
            parse_mode="HTML",
            reply_markup=kb,
        )

        # Автоудаление обоих сообщений (задержка из настроек)
        delay = get_setting("autodel_gallery")
        if delay:
            pm_chat_id = update.effective_chat.id
            user_mid = update.message.message_id
            bot_mid = bot_msg.message_id

            async def _del_gallery(ctx):
                for mid in [user_mid, bot_mid]:
                    try:
                        await ctx.bot.delete_message(pm_chat_id, mid)
                    except Exception:
                        pass

            context.job_queue.run_once(_del_gallery, delay)
        return
    await help_command(update, context)


async def _weekly_best_photo(context) -> None:
    """Каждый понедельник в 00:00 МСК постит лучшее фото за неделю."""
    if not get_setting("weekly_best_photo"):
        return
    main_id = get_main_chat_id()
    if not main_id:
        logger.warning("weekly_best_photo: основная группа не назначена (/settings → Чаты бота)")
        return
    for chat_id in [main_id]:
        try:
            row = get_best_photo_since(days=7, chat_id=chat_id)
            if not row:
                continue
            votes = row["vote_count"]
            avg   = round(row["avg_score"], 1)
            author = "Аноним" if row["anonymous"] else _html_mod.escape(row["author_name"] or "Аноним")
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
                msg = await context.bot.send_video(chat_id=chat_id, video=photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                msg = await context.bot.send_photo(chat_id=chat_id, photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            track_bot_message(chat_id, msg.message_id, caption[:80])
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
            primary_ext = "mp4" if media_type == "video" else "jpg"
            for ext in (primary_ext, "mp4" if primary_ext == "jpg" else "jpg"):
                fpath = os.path.join(photos_dir, f"{key}.{ext}")
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                        deleted_count += 1
                    except OSError as e:
                        logger.warning("cleanup_old_photos: не удалось удалить %s: %s", fpath, e)
        if deleted_count:
            logger.info("cleanup_old_photos: удалено %d файлов", deleted_count)
    except Exception as e:
        logger.error("cleanup_old_photos: %s", e)


async def _handle_edited_message(update, context):
    """При редактировании сообщения — отменяем pending swear job если маты убраны."""
    msg = update.edited_message
    if not msg:
        return
    text = msg.text or ""
    # Если в отредактированном тексте больше нет матов — отменяем запланированный ответ
    if _count_swears(text) == 0:
        chat_id = msg.chat_id
        for job in context.job_queue.get_jobs_by_name(f"swear_{chat_id}"):
            if job.data and job.data.get("message_id") == msg.message_id:
                job.schedule_removal()


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

    # Middleware: maintenance (group=-3) → setup (group=-2) → rate limit (group=-1)
    app.add_handler(
        MessageHandler(filters.COMMAND, _maintenance_guard),
        group=-3,
    )
    app.add_handler(
        MessageHandler(filters.COMMAND & filters.ChatType.GROUPS, _setup_guard),
        group=-2,
    )
    app.add_handler(
        MessageHandler(filters.COMMAND, _rate_limit_guard),
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
    # Единый /cancel — сначала проверяем resend, потом anon
    async def _cancel_command(update, context):
        from commands.resend import _RESEND_WAITING
        if update.effective_user.id in _RESEND_WAITING:
            await resend_cancel(update, context)
        else:
            await handle_anon_cancel(update, context)

    app.add_handler(CommandHandler("cancel", _cancel_command, filters=filters.ChatType.PRIVATE))

    app.add_handler(CommandHandler("gallery",    gallery_command,    filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("clearmedia", clearmedia_command))

    # Скрытые команды владельца — только в личке, не в списке команд
    app.add_handler(CommandHandler("delmsg",       delmsg_command,       filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("resend",       resend_command,       filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("settings",     settings_command,     filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("exportstats",  exportstats_command,  filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("backup",       backup_command,       filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("maintenance",  maintenance_command,  filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("restart",      restart_command,      filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("setavatar",    setavatar_command,    filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("ownerhelp",    ownerhelp_command))

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

    # Кнопка «Закрыть» в уведомлении об итогах голосования
    async def _dismiss_callback(update, context):
        await update.callback_query.answer()
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass

    # Inline-кнопки
    app.add_handler(CallbackQueryHandler(_dismiss_callback,      pattern=r"^dismiss$"))
    app.add_handler(CallbackQueryHandler(delmsg_callback,        pattern=r"^delmsg_"))
    app.add_handler(CallbackQueryHandler(settings_callback,      pattern=r"^stg:"))
    app.add_handler(CallbackQueryHandler(top_callback,           pattern=r"^top_"))
    app.add_handler(CallbackQueryHandler(rate_callback,          pattern=r"^(anon_|rate_|comment_ask_|comment_skip_)"))
    app.add_handler(CallbackQueryHandler(weather_callback,       pattern=r"^w(forecast|refresh):"))
    app.add_handler(CallbackQueryHandler(ownerhelp_pin_callback, pattern=r"^ownerhelp_pin$"))
    app.add_handler(CallbackQueryHandler(clearmedia_callback,    pattern=r"^clearmedia_"))

    # Анонимные сообщения / подпись /rate / resend в личке + трекинг в группах
    async def _maybe_token_reply(update, context):
        if update.effective_chat and update.effective_chat.type == "private":
            # Приоритет: настройки → resend → подпись к /rate → анонимное сообщение
            if await handle_settings_input(update, context):
                return
            if await handle_resend_message(update, context):
                return
            if await handle_rate_comment(update, context):
                return
            await handle_anon_message(update, context)
        else:
            await _track_message(update, context)

    # Трекинг текстовых сообщений (без команд)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _maybe_token_reply))

    # Отмена swear-job при редактировании сообщений (убрали мат → не отвечаем)
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, _handle_edited_message))

    async def on_startup(app):
        await app.bot.set_my_description("Скаут на связи 🟢")
        await app.bot.set_my_short_description("Скаут на связи 🟢")
        await send_restart_done(app)
        # set_my_commands намеренно не вызывается — список команд настраивается
        # вручную через BotFather и не должен перезаписываться при каждом запуске

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

        # Авточистка _cmd_last_used — каждый час убираем записи старше 2 часов
        async def _cleanup_cmd_cooldown(ctx):
            cutoff = time.time() - 7200
            stale = [k for k, v in _cmd_last_used.items() if v < cutoff]
            for k in stale:
                _cmd_last_used.pop(k, None)
            if stale:
                logger.debug("_cmd_last_used: удалено %d устаревших записей", len(stale))

        app.job_queue.run_repeating(_cleanup_cmd_cooldown, interval=3600, first=3600, name="cleanup_cmd_cooldown")

        # Сброс кэша аватаров раз в 24 ч — чтобы обновлять фото профиля
        async def _clear_avatar_cache(ctx):
            _avatar_cache_set.clear()
            logger.debug("_avatar_cache_set: сброшен")

        app.job_queue.run_repeating(_clear_avatar_cache, interval=86400, first=86400, name="clear_avatar_cache")

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
