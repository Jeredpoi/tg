# ==============================================================================
# commands/achievements.py — Система ачивок и достижений (60 штук, 3 категории)
# ==============================================================================

import asyncio
import logging
from database import grant_achievement, get_user_achievements

logger = logging.getLogger(__name__)

# ── Категории ─────────────────────────────────────────────────────────────────

CAT_EASY   = "easy"
CAT_HARD   = "hard"
CAT_SECRET = "secret"

# ── Определения ачивок ────────────────────────────────────────────────────────

ACHIEVEMENTS: dict[str, dict] = {

    # ── ЛЁГКИЕ (20) ──────────────────────────────────────────────────────────

    "first_msg": {
        "icon": "🗣", "name": "Первый шаг",
        "desc": "Написал первое сообщение в чате",
        "hint": "Начни разговор.", "cat": CAT_EASY,
    },
    "msg_10": {
        "icon": "💬", "name": "Разговорчивый",
        "desc": "10 сообщений в чате",
        "hint": "Слова сами собой льются.", "cat": CAT_EASY,
    },
    "msg_100": {
        "icon": "📢", "name": "Болтун",
        "desc": "100 сообщений",
        "hint": "Три цифры — солидно.", "cat": CAT_EASY,
    },
    "first_swear": {
        "icon": "🤬", "name": "Первый мат",
        "desc": "Написал свой первый мат",
        "hint": "Однажды ты не сдержался.", "cat": CAT_EASY,
    },
    "swear_10": {
        "icon": "😤", "name": "Сквернослов",
        "desc": "10 матов в чате",
        "hint": "Экспрессия на максимуме.", "cat": CAT_EASY,
    },
    "streak_3": {
        "icon": "🔥", "name": "На волне",
        "desc": "3 дня подряд в чате",
        "hint": "Три — магическое число.", "cat": CAT_EASY,
    },
    "streak_7": {
        "icon": "⚡", "name": "Неделя",
        "desc": "7 дней подряд в чате",
        "hint": "Семь дней без перерыва.", "cat": CAT_EASY,
    },
    "night_owl": {
        "icon": "🦉", "name": "Сова",
        "desc": "Написал сообщение в 2:00–5:00 МСК",
        "hint": "Когда все спят.", "cat": CAT_EASY,
    },
    "early_bird": {
        "icon": "🐓", "name": "Ранняя пташка",
        "desc": "Написал сообщение в 5:00–7:00 МСК",
        "hint": "Утро вечера мудренее.", "cat": CAT_EASY,
    },
    "monday_warrior": {
        "icon": "⚔️", "name": "Понедельничный воин",
        "desc": "Написал сообщение в понедельник до 9:00 МСК",
        "hint": "Ненавидишь понедельники? А ты попробуй.", "cat": CAT_EASY,
    },
    "midnight_msg": {
        "icon": "🌙", "name": "Полуночник",
        "desc": "Написал сообщение в 00:00–00:05 МСК",
        "hint": "Ровно в полночь.", "cat": CAT_EASY,
    },
    "comeback": {
        "icon": "🔄", "name": "Камбэк",
        "desc": "Вернулся в чат после 7+ дней отсутствия",
        "hint": "Долго тебя не было.", "cat": CAT_EASY,
    },
    "rate_first": {
        "icon": "📸", "name": "Фотограф",
        "desc": "Впервые отправил фото на оценку",
        "hint": "Покажи себя.", "cat": CAT_EASY,
    },
    "rate_winner": {
        "icon": "🥇", "name": "Победитель",
        "desc": "Фото набрало средний рейтинг 8.0+",
        "hint": "Высокая оценка!", "cat": CAT_EASY,
    },
    "swear_storm": {
        "icon": "⚡", "name": "Шторм",
        "desc": "5 и более матов в одном сообщении",
        "hint": "Сконцентрированная экспрессия.", "cat": CAT_EASY,
    },
    "spam_king": {
        "icon": "📨", "name": "Спамер",
        "desc": "50+ сообщений за один день",
        "hint": "Сегодня ты очень активен.", "cat": CAT_EASY,
    },
    "lucky_number": {
        "icon": "🎰", "name": "Счастливчик",
        "desc": "Написал 777-е сообщение в чате",
        "hint": "Везёт тому, кто везёт.", "cat": CAT_EASY,
    },
    "emoji_only": {
        "icon": "😎", "name": "Emoji-говорун",
        "desc": "Отправил сообщение только из эмодзи",
        "hint": "Иногда слова лишние.", "cat": CAT_EASY,
    },
    "debug_user": {
        "icon": "🔧", "name": "Отладчик",
        "desc": "Использовал команду /debug",
        "hint": "Ты знаешь, что ищешь.", "cat": CAT_EASY,
    },
    "first_anon": {
        "icon": "🎭", "name": "Инкогнито",
        "desc": "Впервые отправил анонимное сообщение",
        "hint": "Иногда лучше без имени.", "cat": CAT_EASY,
    },

    # ── СЛОЖНЫЕ (20) ─────────────────────────────────────────────────────────

    "msg_500": {
        "icon": "📣", "name": "Оратор",
        "desc": "500 сообщений в чате",
        "hint": "Полтысячи — не шутки.", "cat": CAT_HARD,
    },
    "msg_1000": {
        "icon": "🎙", "name": "Легенда чата",
        "desc": "1000 сообщений",
        "hint": "Четыре цифры.", "cat": CAT_HARD,
    },
    "msg_2500": {
        "icon": "🗣", "name": "Трибун",
        "desc": "2500 сообщений в чате",
        "hint": "Ты никогда не молчишь.", "cat": CAT_HARD,
    },
    "msg_5000": {
        "icon": "📻", "name": "Вещатель",
        "desc": "5000 сообщений в чате",
        "hint": "Слов больше, чем у словаря.", "cat": CAT_HARD,
    },
    "msg_10000": {
        "icon": "🎤", "name": "Икона чата",
        "desc": "10 000 сообщений — легенда",
        "hint": "Пять цифр. Это серьёзно.", "cat": CAT_HARD,
    },
    "swear_50": {
        "icon": "💀", "name": "Матерщинник",
        "desc": "50 матов в чате",
        "hint": "Полсотни — уже привычка.", "cat": CAT_HARD,
    },
    "swear_200": {
        "icon": "☠️", "name": "Отец матершины",
        "desc": "200 матов в чате",
        "hint": "Двести — это талант.", "cat": CAT_HARD,
    },
    "swear_500": {
        "icon": "💢", "name": "Эксперт по матам",
        "desc": "500 матов — профессионал",
        "hint": "Это уже мастерство.", "cat": CAT_HARD,
    },
    "swear_1000": {
        "icon": "🔥", "name": "Мат-чемпион",
        "desc": "1000 матов. Просто... зачем?",
        "hint": "Тысяча. Это рекорд.", "cat": CAT_HARD,
    },
    "streak_14": {
        "icon": "⚡", "name": "Две недели",
        "desc": "14 дней подряд в чате",
        "hint": "Привычка формируется за 21 день.", "cat": CAT_HARD,
    },
    "streak_30": {
        "icon": "🌟", "name": "Верный",
        "desc": "30 дней подряд в чате",
        "hint": "Месяц без пропусков.", "cat": CAT_HARD,
    },
    "streak_60": {
        "icon": "🌟", "name": "Два месяца",
        "desc": "60 дней подряд в чате",
        "hint": "Настойчивость вознаграждается.", "cat": CAT_HARD,
    },
    "streak_100": {
        "icon": "💎", "name": "Сотня дней",
        "desc": "100 дней подряд — железная воля",
        "hint": "Три цифры упорства.", "cat": CAT_HARD,
    },
    "ach_10": {
        "icon": "🏅", "name": "Коллекционер",
        "desc": "Получил 10 ачивок",
        "hint": "Десять наград — только начало.", "cat": CAT_HARD,
    },
    "ach_25": {
        "icon": "🎖", "name": "Охотник за ачивками",
        "desc": "Получил 25 ачивок",
        "hint": "Уже четверть пути.", "cat": CAT_HARD,
    },
    "ach_40": {
        "icon": "🏆", "name": "Ветеран",
        "desc": "Получил 40 ачивок",
        "hint": "Почти всё.", "cat": CAT_HARD,
    },
    "ach_50": {
        "icon": "🌈", "name": "Мастер",
        "desc": "Получил 50 ачивок",
        "hint": "Пятьдесят — магическое число.", "cat": CAT_HARD,
    },
    "rate_5": {
        "icon": "🎨", "name": "Фотогеник",
        "desc": "Отправил 5 фото на оценку",
        "hint": "Камера тебя любит.", "cat": CAT_HARD,
    },
    "rate_perfect": {
        "icon": "💯", "name": "Перфекционист",
        "desc": "Фото набрало средний рейтинг 9.0+",
        "hint": "Идеал существует.", "cat": CAT_HARD,
    },
    "all_easy": {
        "icon": "✨", "name": "Полный набор",
        "desc": "Получил все лёгкие ачивки",
        "hint": "Завершил первую главу.", "cat": CAT_HARD,
    },

    # ── СЕКРЕТНЫЕ (20) ────────────────────────────────────────────────────────

    "time_1337": {
        "icon": "🕰", "name": "13:37",
        "desc": "Написал сообщение ровно в 13:37 МСК",
        "hint": "Иногда время — это знак.", "cat": CAT_SECRET, "secret": True,
    },
    "mirror": {
        "icon": "🎭", "name": "Зеркало",
        "desc": "Написал точно такое же сообщение, как предыдущее в чате",
        "hint": "Ты уверен, что это не отражение?", "cat": CAT_SECRET, "secret": True,
    },
    "minds_meet": {
        "icon": "🧠", "name": "Мысли сходятся",
        "desc": "Твоё сообщение совпало с чужим из последних 5 минут",
        "hint": "Кто-то думает так же, как ты.", "cat": CAT_SECRET, "secret": True,
    },
    "bullseye": {
        "icon": "🎯", "name": "Попал",
        "desc": "Ответил на сообщение быстрее чем за 3 секунды",
        "hint": "Иногда скорость решает.", "cat": CAT_SECRET, "secret": True,
    },
    "rare_plus": {
        "icon": "🎲", "name": "Редкость+",
        "desc": "Получил случайным образом (0.25%)",
        "hint": "Не всё можно получить усилием.", "cat": CAT_SECRET, "secret": True,
    },
    "deja_vu": {
        "icon": "🔁", "name": "Дежавю",
        "desc": "Написал то же сообщение, что и раньше",
        "hint": "Ты это уже говорил…", "cat": CAT_SECRET, "secret": True,
    },
    "void": {
        "icon": "🕳", "name": "Пустота",
        "desc": "Написал сообщение, которое состоит только из пробелов или невидимых символов",
        "hint": "Иногда ничего — это тоже что-то.", "cat": CAT_SECRET, "secret": True,
    },
    "too_early": {
        "icon": "⚡", "name": "Слишком рано",
        "desc": "Написал сообщение раньше 4:00 МСК",
        "hint": "Ты опередил момент.", "cat": CAT_SECRET, "secret": True,
    },
    "too_late": {
        "icon": "⏳", "name": "Слишком поздно",
        "desc": "Написал первое сообщение дня после 23:59",
        "hint": "Ты вспомнил… но поздно.", "cat": CAT_SECRET, "secret": True,
    },
    "no_words": {
        "icon": "🧠", "name": "Без слов",
        "desc": "Отправил сообщение без единой буквы",
        "hint": "Слова лишние.", "cat": CAT_SECRET, "secret": True,
    },
    "pon": {
        "icon": "🐸", "name": "пон",
        "desc": "Написал «пон» (и только «пон»)",
        "hint": "Ты понял.", "cat": CAT_SECRET, "secret": True,
    },
    "lol_ach": {
        "icon": "💀", "name": "лол",
        "desc": "Написал «лол» (и только «лол»)",
        "hint": "Очень смешно.", "cat": CAT_SECRET, "secret": True,
    },
    "moai": {
        "icon": "🗿", "name": "🗿",
        "desc": "Написал только 🗿",
        "hint": "🗿", "cat": CAT_SECRET, "secret": True,
    },
    "thrice": {
        "icon": "🔄", "name": "Трижды",
        "desc": "Написал одно и то же три раза подряд",
        "hint": "Повтори ещё раз.", "cat": CAT_SECRET, "secret": True,
    },
    "glitch": {
        "icon": "🧬", "name": "Глюк",
        "desc": "Отправил палиндром длиннее 5 символов",
        "hint": "Система дала сбой.", "cat": CAT_SECRET, "secret": True,
    },
    "speedrun": {
        "icon": "🚀", "name": "Speedrun",
        "desc": "5 сообщений менее чем за 10 секунд",
        "hint": "Ты слишком быстрый.", "cat": CAT_SECRET, "secret": True,
    },
    "i_see_all": {
        "icon": "👁", "name": "Я вижу всё",
        "desc": "Написал «я вижу всё» (примерно)",
        "hint": "Теперь ты знаешь.", "cat": CAT_SECRET, "secret": True,
    },
    "decoded": {
        "icon": "🧠", "name": "Разгадал систему",
        "desc": "Написал «я знаю правила» или похожее",
        "hint": "Ты понял правила.", "cat": CAT_SECRET, "secret": True,
    },
    "ultra_hidden": {
        "icon": "🧩", "name": "???",
        "desc": "Ультра-секретная ачивка",
        "hint": "Ты точно уверен, что всё нашёл?", "cat": CAT_SECRET, "secret": True,
    },
    "absolute": {
        "icon": "👑", "name": "Абсолют",
        "desc": "Получил все 59 других ачивок",
        "hint": "Ты дошёл до конца.", "cat": CAT_SECRET, "secret": True,
    },
}

# ── Вспомогательные множества ─────────────────────────────────────────────────

_EASY_IDS   = frozenset(k for k, v in ACHIEVEMENTS.items() if v["cat"] == CAT_EASY)
_HARD_IDS   = frozenset(k for k, v in ACHIEVEMENTS.items() if v["cat"] == CAT_HARD)
_SECRET_IDS = frozenset(k for k, v in ACHIEVEMENTS.items() if v["cat"] == CAT_SECRET)
_ALL_IDS    = frozenset(ACHIEVEMENTS.keys())

# ── Счётчики для display ──────────────────────────────────────────────────────

_SECRET_COUNT = len(_SECRET_IDS)

# ── Пороги ────────────────────────────────────────────────────────────────────

_MSG_THRESHOLDS = [
    (1,     "first_msg"),
    (10,    "msg_10"),
    (100,   "msg_100"),
    (500,   "msg_500"),
    (1000,  "msg_1000"),
    (2500,  "msg_2500"),
    (5000,  "msg_5000"),
    (10000, "msg_10000"),
]

_SWEAR_THRESHOLDS = [
    (1,    "first_swear"),
    (10,   "swear_10"),
    (50,   "swear_50"),
    (200,  "swear_200"),
    (500,  "swear_500"),
    (1000, "swear_1000"),
]

_STREAK_THRESHOLDS = [
    (3,   "streak_3"),
    (7,   "streak_7"),
    (14,  "streak_14"),
    (30,  "streak_30"),
    (60,  "streak_60"),
    (100, "streak_100"),
]

_ACH_COUNT_THRESHOLDS = [
    (10, "ach_10"),
    (25, "ach_25"),
    (40, "ach_40"),
    (50, "ach_50"),
]

# ── Meta IDs (не вызывают рекурсию) ──────────────────────────────────────────

_META_IDS = frozenset(["ach_10", "ach_25", "ach_40", "ach_50", "all_easy", "absolute"])


# ── Анонс и выдача ────────────────────────────────────────────────────────────

async def _announce(bot, chat_id: int, user_name: str, ach_id: str) -> None:
    ach = ACHIEVEMENTS.get(ach_id)
    if not ach:
        return
    text = (
        f"🏆 <b>{user_name}</b> получил ачивку "
        f"{ach['icon']} <b>{ach['name']}</b>!\n"
        f"<i>{ach['desc']}</i>"
    )
    try:
        msg = await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        async def _delete():
            await asyncio.sleep(10)
            try:
                await bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
        asyncio.create_task(_delete())
    except Exception as e:
        logger.warning("achievements: не удалось отправить анонс %s: %s", ach_id, e)


async def _grant_if_new(
    bot, chat_id: int, user_id: int, user_name: str, ach_id: str,
    _in_meta: bool = False,
) -> bool:
    """Grant achievement and announce if newly earned. Returns True if newly granted."""
    granted = grant_achievement(user_id, chat_id, ach_id)
    if granted:
        await _announce(bot, chat_id, user_name, ach_id)
        if not _in_meta and ach_id not in _META_IDS:
            await _check_meta_achievements(bot, chat_id, user_id, user_name)
    return granted


async def _check_meta_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
) -> None:
    """Checks and grants meta-achievements (counts, all_easy, absolute)."""
    rows = get_user_achievements(user_id, chat_id)
    earned_ids = {r["achievement_id"] for r in rows if r["achievement_id"] in ACHIEVEMENTS}
    total = len(earned_ids)

    for threshold, ach_id in _ACH_COUNT_THRESHOLDS:
        if total >= threshold:
            await _grant_if_new(bot, chat_id, user_id, user_name, ach_id, _in_meta=True)

    if _EASY_IDS.issubset(earned_ids):
        await _grant_if_new(bot, chat_id, user_id, user_name, "all_easy", _in_meta=True)

    non_absolute = _ALL_IDS - {"absolute"}
    if non_absolute.issubset(earned_ids):
        await _grant_if_new(bot, chat_id, user_id, user_name, "absolute", _in_meta=True)


# ── Публичные check-функции ───────────────────────────────────────────────────

async def check_message_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
    msg_count: int, swear_count: int,
) -> None:
    """Проверяет ачивки по сообщениям и матам после каждого сообщения."""
    for threshold, ach_id in _MSG_THRESHOLDS:
        if msg_count >= threshold:
            await _grant_if_new(bot, chat_id, user_id, user_name, ach_id)

    for threshold, ach_id in _SWEAR_THRESHOLDS:
        if swear_count >= threshold:
            await _grant_if_new(bot, chat_id, user_id, user_name, ach_id)


async def check_streak_achievements(
    bot, chat_id: int, user_id: int, user_name: str, streak: int,
) -> None:
    """Проверяет ачивки по стрику активности."""
    for threshold, ach_id in _STREAK_THRESHOLDS:
        if streak >= threshold:
            await _grant_if_new(bot, chat_id, user_id, user_name, ach_id)


async def check_king_achievements(
    bot, chat_id: int, user_id: int, user_name: str, king_count: int,
) -> None:
    """No-op: король-ачивки удалены."""
    pass


async def check_time_achievements(
    bot, chat_id: int, user_id: int, user_name: str, dt,
) -> None:
    """Проверяет ачивки по времени сообщения (dt — datetime в МСК)."""
    hour    = dt.hour
    minute  = dt.minute
    weekday = dt.weekday()  # 0 = Monday

    if hour < 4:
        await _grant_if_new(bot, chat_id, user_id, user_name, "too_early")
    if 2 <= hour < 5:
        await _grant_if_new(bot, chat_id, user_id, user_name, "night_owl")
    if 5 <= hour < 7:
        await _grant_if_new(bot, chat_id, user_id, user_name, "early_bird")
    if weekday == 0 and hour < 9:
        await _grant_if_new(bot, chat_id, user_id, user_name, "monday_warrior")
    if hour == 0 and minute < 5:
        await _grant_if_new(bot, chat_id, user_id, user_name, "midnight_msg")
    if hour == 23 and minute == 59:
        await _grant_if_new(bot, chat_id, user_id, user_name, "too_late")
    if hour == 13 and minute == 37:
        await _grant_if_new(bot, chat_id, user_id, user_name, "time_1337")


async def check_single_message_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
    swear_in_msg: int, total_chat_msgs: int,
) -> None:
    """Проверяет ачивки, зависящие от одного конкретного сообщения."""
    if swear_in_msg >= 5:
        await _grant_if_new(bot, chat_id, user_id, user_name, "swear_storm")
    if total_chat_msgs == 777:
        await _grant_if_new(bot, chat_id, user_id, user_name, "lucky_number")


async def check_activity_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
    daily_count: int, days_since_last: int,
) -> None:
    """Проверяет ачивки по активности: спам за день и камбэк."""
    if daily_count >= 50:
        await _grant_if_new(bot, chat_id, user_id, user_name, "spam_king")
    if days_since_last >= 7:
        await _grant_if_new(bot, chat_id, user_id, user_name, "comeback")


async def check_rate_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
    is_first: bool = False,
    avg_rating: float | None = None,
    total_published: int = 0,
) -> None:
    """Проверяет ачивки, связанные с оценкой фото."""
    if is_first:
        await _grant_if_new(bot, chat_id, user_id, user_name, "rate_first")
    if total_published >= 5:
        await _grant_if_new(bot, chat_id, user_id, user_name, "rate_5")
    if avg_rating is not None and avg_rating >= 8.0:
        await _grant_if_new(bot, chat_id, user_id, user_name, "rate_winner")
    if avg_rating is not None and avg_rating >= 9.0:
        await _grant_if_new(bot, chat_id, user_id, user_name, "rate_perfect")


async def check_simple_achievements(
    bot, chat_id: int, user_id: int, user_name: str, ach_id: str,
) -> None:
    """Выдаёт конкретную ачивку напрямую (для debug_user, first_anon и т.п.)."""
    await _grant_if_new(bot, chat_id, user_id, user_name, ach_id)


async def check_secret_text_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
    text: str,
    reply_delta_secs: float | None,
    prev_chat_text: str | None,
    prev_user_text: str | None,
    recent_chat_texts: list[str],
    user_consecutive_count: int,
    user_recent_count: int,
    silence_hours: float,
) -> None:
    """
    Проверяет секретные ачивки по тексту сообщения и контексту.

    Параметры:
    - text: текст текущего сообщения
    - reply_delta_secs: секунды от исходного сообщения до ответа (None если не реплай)
    - prev_chat_text: последнее сообщение другого пользователя в чате (до этого)
    - prev_user_text: предыдущее сообщение этого пользователя
    - recent_chat_texts: тексты сообщений других пользователей за последние 5 минут
    - user_consecutive_count: сколько раз подряд пользователь пишет один и тот же текст
    - user_recent_count: кол-во сообщений за последние 10 сек
    - silence_hours: часов прошло с последнего сообщения пользователя в чате
    """
    import random
    import re

    t = text.strip() if text else ""
    t_lower = t.lower()

    # mirror — то же, что предыдущее сообщение в чате
    if prev_chat_text and t == prev_chat_text:
        await _grant_if_new(bot, chat_id, user_id, user_name, "mirror")

    # minds_meet — текст совпадает с любым из последних 5 мин в чате
    if t and any(t == rt for rt in recent_chat_texts):
        await _grant_if_new(bot, chat_id, user_id, user_name, "minds_meet")

    # bullseye — ответ быстрее 3 сек
    if reply_delta_secs is not None and reply_delta_secs < 3.0:
        await _grant_if_new(bot, chat_id, user_id, user_name, "bullseye")

    # rare_plus — 0.25% случайно
    if random.random() < 0.0025:
        await _grant_if_new(bot, chat_id, user_id, user_name, "rare_plus")

    # deja_vu — пользователь раньше писал то же самое
    if prev_user_text and t and t == prev_user_text:
        await _grant_if_new(bot, chat_id, user_id, user_name, "deja_vu")

    # void — только пробелы / невидимые символы
    if t_lower == "" and text and not text.strip():
        await _grant_if_new(bot, chat_id, user_id, user_name, "void")

    # no_words — нет ни одной буквы
    if text and not re.search(r'[a-zA-Zа-яёА-ЯЁ]', text):
        await _grant_if_new(bot, chat_id, user_id, user_name, "no_words")

    # emoji_only — только эмодзи
    if text:
        stripped = re.sub(
            r'[\U00010000-\U0010ffff\U00002700-\U000027BF\U0000FE00-\U0000FE0F'
            r'\U0001F000-\U0001FFFF\u200d\ufe0f\u20e3]+', '', text.strip()
        )
        if not stripped and text.strip():
            await _grant_if_new(bot, chat_id, user_id, user_name, "emoji_only")

    # pon
    if t_lower == "пон":
        await _grant_if_new(bot, chat_id, user_id, user_name, "pon")

    # lol
    if t_lower == "лол":
        await _grant_if_new(bot, chat_id, user_id, user_name, "lol_ach")

    # moai
    if t == "🗿":
        await _grant_if_new(bot, chat_id, user_id, user_name, "moai")

    # thrice — три раза подряд одно и то же
    if user_consecutive_count >= 3:
        await _grant_if_new(bot, chat_id, user_id, user_name, "thrice")

    # glitch — палиндром >= 5 символов
    clean = re.sub(r'[^а-яёА-ЯЁa-zA-Z0-9]', '', t.lower())
    if len(clean) >= 5 and clean == clean[::-1]:
        await _grant_if_new(bot, chat_id, user_id, user_name, "glitch")

    # speedrun — 5 сообщений за 10 сек
    if user_recent_count >= 5:
        await _grant_if_new(bot, chat_id, user_id, user_name, "speedrun")

    # i_see_all
    if re.search(r'я\s+вижу\s+всё', t_lower) or re.search(r'я\s+всё\s+вижу', t_lower):
        await _grant_if_new(bot, chat_id, user_id, user_name, "i_see_all")

    # decoded
    if re.search(r'я\s+(знаю|понял|разгадал)\s+(правила|систему|всё)', t_lower):
        await _grant_if_new(bot, chat_id, user_id, user_name, "decoded")

    # ultra_hidden — сообщение является числом 42
    if t.strip() == "42":
        await _grant_if_new(bot, chat_id, user_id, user_name, "ultra_hidden")


# ── Пагинация для /achievements ───────────────────────────────────────────────

def get_achievements_page(
    user_id: int, chat_id: int, category: str, page: int, per_page: int = 5,
) -> dict:
    """
    Возвращает словарь с данными страницы ачивок.
    {
        "items": [...],  # список ачивок на странице
        "page": int,
        "total_pages": int,
        "earned_count": int,
        "total_count": int,
    }
    Каждый item: {"id": str, "earned": bool, "icon": str, "name": str, "desc": str, "hint": str}
    """
    rows = get_user_achievements(user_id, chat_id)
    earned_ids = {r["achievement_id"] for r in rows}

    cat_ids = [
        ach_id for ach_id, ach in ACHIEVEMENTS.items()
        if ach["cat"] == category
    ]

    earned_in_cat = sum(1 for ach_id in cat_ids if ach_id in earned_ids)
    total_in_cat  = len(cat_ids)

    total_pages = max(1, (total_in_cat + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    page_ids = cat_ids[start : start + per_page]

    items = []
    for ach_id in page_ids:
        ach = ACHIEVEMENTS[ach_id]
        earned = ach_id in earned_ids
        items.append({
            "id":     ach_id,
            "earned": earned,
            "icon":   ach["icon"],
            "name":   ach["name"] if (earned or not ach.get("secret")) else "???",
            "desc":   ach["desc"],
            "hint":   ach.get("hint", ""),
            "secret": ach.get("secret", False),
        })

    return {
        "items":        items,
        "page":         page,
        "total_pages":  total_pages,
        "earned_count": earned_in_cat,
        "total_count":  total_in_cat,
    }


# ── Форматирование для /stats ─────────────────────────────────────────────────

def format_achievements(user_id: int, chat_id: int) -> str:
    """Возвращает строку с ачивками для /stats. Пустая строка если нет."""
    rows = get_user_achievements(user_id, chat_id)
    if not rows:
        return ""

    earned_ids = {r["achievement_id"] for r in rows if r["achievement_id"] in ACHIEVEMENTS}

    icons = " · ".join(ACHIEVEMENTS[ach_id]["icon"] for ach_id in earned_ids)

    total_earned   = len(earned_ids)
    earned_secrets = sum(1 for ach_id in earned_ids if ACHIEVEMENTS[ach_id].get("secret"))

    lines = [f"🏆 Ачивки ({total_earned}): {icons}"]
    lines.append(f"🔒 Секретных: {earned_secrets} из {_SECRET_COUNT}")
    return "\n".join(lines)
