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
    "first_msg":  {"icon": "🗣",  "name": "Первый шаг",   "desc": "Написал первое сообщение в чате"},
    "msg_10":     {"icon": "💬",  "name": "Разговорчивый","desc": "10 сообщений"},
    "msg_100":    {"icon": "📢",  "name": "Болтун",       "desc": "100 сообщений"},
    "msg_500":    {"icon": "📣",  "name": "Оратор",       "desc": "500 сообщений"},
    "msg_1000":   {"icon": "🎙",  "name": "Легенда чата", "desc": "1000 сообщений"},
    # Маты
    "first_swear":{"icon": "🤬",  "name": "Первый мат",   "desc": "Написал первый мат"},
    "swear_10":   {"icon": "😤",  "name": "Сквернослов",  "desc": "10 матов"},
    "swear_50":   {"icon": "💀",  "name": "Матерщинник",  "desc": "50 матов"},
    "swear_200":  {"icon": "☠️",  "name": "Отец матершины","desc": "200 матов"},
    # Стрик активности
    "streak_3":   {"icon": "🔥",  "name": "На волне",     "desc": "3 дня подряд в чате"},
    "streak_7":   {"icon": "⚡",  "name": "Завсегдатай",  "desc": "7 дней подряд в чате"},
    "streak_30":  {"icon": "🌟",  "name": "Верный",       "desc": "30 дней подряд в чате"},
    # Корона
    "first_king": {"icon": "👑",  "name": "Первый трон",  "desc": "Стал королём дня впервые"},
    "king_5":     {"icon": "👸",  "name": "Постоянный король","desc": "5 раз становился королём дня"},
}

# Пороги по сообщениям: (порог, achievement_id)
_MSG_THRESHOLDS = [
    (1, "first_msg"), (10, "msg_10"), (100, "msg_100"),
    (500, "msg_500"), (1000, "msg_1000"),
]

# Пороги по матам
_SWEAR_THRESHOLDS = [
    (1, "first_swear"), (10, "swear_10"), (50, "swear_50"), (200, "swear_200"),
]

# Пороги по стрику
_STREAK_THRESHOLDS = [
    (3, "streak_3"), (7, "streak_7"), (30, "streak_30"),
]


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


async def check_message_achievements(
    bot, chat_id: int, user_id: int, user_name: str,
    msg_count: int, swear_count: int,
) -> None:
    """Проверяет ачивки по сообщениям и матам после каждого сообщения."""
    for threshold, ach_id in _MSG_THRESHOLDS:
        if msg_count >= threshold:
            if grant_achievement(user_id, chat_id, ach_id):
                await _announce(bot, chat_id, user_name, ach_id)

    for threshold, ach_id in _SWEAR_THRESHOLDS:
        if swear_count >= threshold:
            if grant_achievement(user_id, chat_id, ach_id):
                await _announce(bot, chat_id, user_name, ach_id)


async def check_streak_achievements(
    bot, chat_id: int, user_id: int, user_name: str, streak: int,
) -> None:
    """Проверяет ачивки по стрику активности."""
    for threshold, ach_id in _STREAK_THRESHOLDS:
        if streak >= threshold:
            if grant_achievement(user_id, chat_id, ach_id):
                await _announce(bot, chat_id, user_name, ach_id)


async def check_king_achievements(
    bot, chat_id: int, user_id: int, user_name: str, king_count: int,
) -> None:
    """Проверяет ачивки за корону (вызывается при назначении короля)."""
    thresholds = [(1, "first_king"), (5, "king_5")]
    for threshold, ach_id in thresholds:
        if king_count >= threshold:
            if grant_achievement(user_id, chat_id, ach_id):
                await _announce(bot, chat_id, user_name, ach_id)


# ── Форматирование для /stats ─────────────────────────────────────────────────

def format_achievements(user_id: int, chat_id: int) -> str:
    """Возвращает строку с ачивками для /stats. Пустая строка если нет."""
    rows = get_user_achievements(user_id, chat_id)
    if not rows:
        return ""
    icons = " ".join(
        ACHIEVEMENTS[r["achievement_id"]]["icon"]
        for r in rows
        if r["achievement_id"] in ACHIEVEMENTS
    )
    count = len(rows)
    return f"🏆 Ачивки ({count}): {icons}"
