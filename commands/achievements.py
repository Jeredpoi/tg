# ==============================================================================
# commands/achievements.py — Система ачивок и достижений
# ==============================================================================

import asyncio
import logging
from database import grant_achievement, get_user_achievements

logger = logging.getLogger(__name__)

# ── Определения ачивок ────────────────────────────────────────────────────────

ACHIEVEMENTS: dict[str, dict] = {
    # Сообщения
    "first_msg":  {"icon": "🗣",  "name": "Первый шаг",    "desc": "Написал первое сообщение в чате"},
    "msg_10":     {"icon": "💬",  "name": "Разговорчивый", "desc": "10 сообщений"},
    "msg_100":    {"icon": "📢",  "name": "Болтун",        "desc": "100 сообщений"},
    "msg_500":    {"icon": "📣",  "name": "Оратор",        "desc": "500 сообщений"},
    "msg_1000":   {"icon": "🎙",  "name": "Легенда чата",  "desc": "1000 сообщений"},
    "msg_2500":   {"icon": "🗣",  "name": "Трибун",        "desc": "2500 сообщений в чате"},
    "msg_5000":   {"icon": "📻",  "name": "Вещатель",      "desc": "5000 сообщений в чате"},
    "msg_10000":  {"icon": "🎤",  "name": "Икона чата",    "desc": "10 000 сообщений — легенда"},
    # Маты
    "first_swear": {"icon": "🤬", "name": "Первый мат",       "desc": "Написал первый мат"},
    "swear_10":    {"icon": "😤", "name": "Сквернослов",      "desc": "10 матов"},
    "swear_50":    {"icon": "💀", "name": "Матерщинник",      "desc": "50 матов"},
    "swear_200":   {"icon": "☠️", "name": "Отец матершины",   "desc": "200 матов"},
    "swear_500":   {"icon": "💢", "name": "Эксперт по матам", "desc": "500 матов — профессионал"},
    "swear_1000":  {"icon": "🔥", "name": "Мат-чемпион",      "desc": "1000 матов. Просто... зачем?"},
    # Стрик активности
    "streak_3":   {"icon": "🔥", "name": "На волне",      "desc": "3 дня подряд в чате"},
    "streak_7":   {"icon": "⚡", "name": "Завсегдатай",   "desc": "7 дней подряд в чате"},
    "streak_14":  {"icon": "⚡", "name": "Две недели",    "desc": "14 дней подряд в чате"},
    "streak_30":  {"icon": "🌟", "name": "Верный",        "desc": "30 дней подряд в чате"},
    "streak_60":  {"icon": "🌟", "name": "Два месяца",    "desc": "60 дней подряд в чате"},
    "streak_100": {"icon": "💎", "name": "Сотня дней",    "desc": "100 дней подряд — железная воля"},
    # Корона
    "first_king": {"icon": "👑", "name": "Первый трон",       "desc": "Стал королём дня впервые"},
    "king_5":     {"icon": "👸", "name": "Постоянный король", "desc": "5 раз становился королём дня"},
    "king_10":    {"icon": "🏰", "name": "Монарх",            "desc": "10 раз стал королём дня"},
    "king_30":    {"icon": "👹", "name": "Тиран",             "desc": "30 раз стал королём дня"},
    # Оценки фото
    "rate_first":  {"icon": "📸", "name": "Фотограф",   "desc": "Впервые отправил фото на оценку"},
    "rate_winner": {"icon": "🥇", "name": "Победитель", "desc": "Фото набрало средний рейтинг 8.0+"},
    # Секретные
    "night_owl":      {"icon": "🦉",  "name": "Сова",                "desc": "Написал сообщение глубокой ночью (2:00–5:00 МСК)",  "secret": True},
    "early_bird":     {"icon": "🐓",  "name": "Ранняя пташка",       "desc": "Написал сообщение ранним утром (5:00–7:00 МСК)",    "secret": True},
    "monday_warrior": {"icon": "⚔️", "name": "Понедельничный воин", "desc": "Написал сообщение в понедельник до 9:00",           "secret": True},
    "spam_king":      {"icon": "💬",  "name": "Спамер",              "desc": "50+ сообщений за один день",                        "secret": True},
    "lucky_number":   {"icon": "🎰",  "name": "Счастливчик",         "desc": "Написал 777-е сообщение в чате",                    "secret": True},
    "midnight_msg":   {"icon": "🌙",  "name": "Полуночник",          "desc": "Написал ровно в полночь (00:00–00:05 МСК)",         "secret": True},
    "swear_storm":    {"icon": "⚡",  "name": "Шторм",               "desc": "5+ матов в одном сообщении",                        "secret": True},
    "comeback":       {"icon": "🔄",  "name": "Камбэк",              "desc": "Вернулся в чат после 7+ дней отсутствия",           "secret": True},
}

# Пороги по сообщениям: (порог, achievement_id)
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

# Пороги по матам
_SWEAR_THRESHOLDS = [
    (1,    "first_swear"),
    (10,   "swear_10"),
    (50,   "swear_50"),
    (200,  "swear_200"),
    (500,  "swear_500"),
    (1000, "swear_1000"),
]

# Пороги по стрику
_STREAK_THRESHOLDS = [
    (3,   "streak_3"),
    (7,   "streak_7"),
    (14,  "streak_14"),
    (30,  "streak_30"),
    (60,  "streak_60"),
    (100, "streak_100"),
]

# Число секретных ачивок
_SECRET_COUNT = sum(1 for a in ACHIEVEMENTS.values() if a.get("secret"))


# ── Выдача и анонс ────────────────────────────────────────────────────────────

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
        # Автоудаление через 10 секунд — не засоряем чат
        async def _delete():
            await asyncio.sleep(10)
            try:
                await bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
        asyncio.create_task(_delete())
    except Exception as e:
        logger.warning("achievements: не удалось отправить анонс %s: %s", ach_id, e)


async def _grant_if_new(bot, chat_id: int, user_id: int, user_name: str, ach_id: str) -> bool:
    """Grant achievement and announce if newly earned. Returns True if newly granted."""
    granted = grant_achievement(user_id, chat_id, ach_id)
    if granted:
        await _announce(bot, chat_id, user_name, ach_id)
    return granted


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
    """Проверяет ачивки за корону (вызывается при назначении короля)."""
    thresholds = [(1, "first_king"), (5, "king_5"), (10, "king_10"), (30, "king_30")]
    for threshold, ach_id in thresholds:
        if king_count >= threshold:
            await _grant_if_new(bot, chat_id, user_id, user_name, ach_id)


async def check_time_achievements(
    bot, chat_id: int, user_id: int, user_name: str, dt,
) -> None:
    """Проверяет секретные ачивки по времени отправки сообщения.

    dt — datetime объект в MSK-таймзоне.
    """
    hour = dt.hour
    minute = dt.minute
    weekday = dt.weekday()  # 0 = Monday

    if 2 <= hour < 5:
        if await _grant_if_new(bot, chat_id, user_id, user_name, "night_owl"):
            return
    if 5 <= hour < 7:
        if await _grant_if_new(bot, chat_id, user_id, user_name, "early_bird"):
            return
    if weekday == 0 and hour < 9:
        if await _grant_if_new(bot, chat_id, user_id, user_name, "monday_warrior"):
            return
    if hour == 0 and minute < 5:
        if await _grant_if_new(bot, chat_id, user_id, user_name, "midnight_msg"):
            return


async def check_single_message_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
    swear_in_msg: int, total_chat_msgs: int,
) -> None:
    """Проверяет секретные ачивки, зависящие от одного конкретного сообщения."""
    if swear_in_msg >= 5:
        await _grant_if_new(bot, chat_id, user_id, user_name, "swear_storm")
    if total_chat_msgs == 777:
        await _grant_if_new(bot, chat_id, user_id, user_name, "lucky_number")


async def check_activity_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
    daily_count: int, days_since_last: int,
) -> None:
    """Проверяет секретные ачивки по активности: спам за день и камбэк."""
    if daily_count >= 50:
        await _grant_if_new(bot, chat_id, user_id, user_name, "spam_king")
    if days_since_last >= 7:
        await _grant_if_new(bot, chat_id, user_id, user_name, "comeback")


async def check_rate_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
    is_first: bool = False, avg_rating: float | None = None,
) -> None:
    """Проверяет ачивки, связанные с оценкой фото."""
    if is_first:
        await _grant_if_new(bot, chat_id, user_id, user_name, "rate_first")
    if avg_rating is not None and avg_rating >= 8.0:
        await _grant_if_new(bot, chat_id, user_id, user_name, "rate_winner")


# ── Форматирование для /stats ─────────────────────────────────────────────────

def format_achievements(user_id: int, chat_id: int) -> str:
    """Возвращает строку с ачивками для /stats. Пустая строка если нет."""
    rows = get_user_achievements(user_id, chat_id)
    if not rows:
        return ""

    earned_ids = {r["achievement_id"] for r in rows if r["achievement_id"] in ACHIEVEMENTS}

    icons = " · ".join(
        ACHIEVEMENTS[ach_id]["icon"]
        for ach_id in earned_ids
    )

    total_earned = len(earned_ids)
    earned_secrets = sum(
        1 for ach_id in earned_ids
        if ACHIEVEMENTS[ach_id].get("secret")
    )

    lines = [f"🏆 Ачивки ({total_earned}): {icons}"]
    lines.append(f"🔒 Секретных: {earned_secrets} из {_SECRET_COUNT}")
    return "\n".join(lines)
