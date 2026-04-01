# ==============================================================================
# commands/achievements.py — Система ачивок и достижений
# ==============================================================================

import asyncio
import datetime
import logging
import re
from database import grant_achievement, get_user_achievements

logger = logging.getLogger(__name__)
_MSK = datetime.timezone(datetime.timedelta(hours=3))


# ── Определения ачивок ────────────────────────────────────────────────────────

ACHIEVEMENTS: dict[str, dict] = {
    # Сообщения
    "first_msg": {"icon": "🗣", "name": "Первый шаг", "desc": "Написал первое сообщение в чате"},
    "msg_10": {"icon": "💬", "name": "Разговорчивый", "desc": "10 сообщений"},
    "msg_25": {"icon": "📝", "name": "На связи", "desc": "25 сообщений"},
    "msg_50": {"icon": "📨", "name": "Постоянный гость", "desc": "50 сообщений"},
    "msg_100": {"icon": "📢", "name": "Болтун", "desc": "100 сообщений"},
    "msg_250": {"icon": "📡", "name": "Эфир открыт", "desc": "250 сообщений"},
    "msg_500": {"icon": "📣", "name": "Оратор", "desc": "500 сообщений"},
    "msg_1000": {"icon": "🎙", "name": "Легенда чата", "desc": "1000 сообщений"},
    "msg_2500": {"icon": "🏟", "name": "Голос канала", "desc": "2500 сообщений"},
    "msg_5000": {"icon": "🌋", "name": "Поток сознания", "desc": "5000 сообщений"},
    "msg_10000": {"icon": "🛰", "name": "Архитектор чата", "desc": "10000 сообщений"},
    # Маты
    "first_swear": {"icon": "🤬", "name": "Первый мат", "desc": "Написал первый мат"},
    "swear_10": {"icon": "😤", "name": "Сквернослов", "desc": "10 матов"},
    "swear_25": {"icon": "🧨", "name": "На взводе", "desc": "25 матов"},
    "swear_50": {"icon": "💀", "name": "Матерщинник", "desc": "50 матов"},
    "swear_100": {"icon": "⚠️", "name": "Ругатель", "desc": "100 матов"},
    "swear_200": {"icon": "☠️", "name": "Отец матершины", "desc": "200 матов"},
    "swear_500": {"icon": "🧱", "name": "Без фильтра", "desc": "500 матов"},
    # Стрик активности
    "streak_3": {"icon": "🔥", "name": "На волне", "desc": "3 дня подряд в чате"},
    "streak_7": {"icon": "⚡", "name": "Завсегдатай", "desc": "7 дней подряд в чате"},
    "streak_14": {"icon": "📆", "name": "Двухнедельник", "desc": "14 дней подряд в чате"},
    "streak_30": {"icon": "🌟", "name": "Верный", "desc": "30 дней подряд в чате"},
    "streak_60": {"icon": "🛡", "name": "Несгибаемый", "desc": "60 дней подряд в чате"},
    "streak_100": {"icon": "🏔", "name": "Железная дисциплина", "desc": "100 дней подряд в чате"},
    # Секретные за фразы/упоминания
    "secret_unknown_cmd": {"icon": "❓", "name": "Заклинатель белиберды", "desc": "Впервые написал неизвестную команду"},
    "secret_call_dad": {"icon": "🫡", "name": "Папочка, ты тут?", "desc": "Упомянул бота и позвал папочку"},
    "secret_respect_bot": {"icon": "🤝", "name": "Респект машине", "desc": "Похвалил бота в сообщении с упоминанием"},
    "secret_signal_check": {"icon": "📡", "name": "Проверка связи", "desc": "Проверил связь с ботом по тегу"},
    "secret_night_ping": {"icon": "🌙", "name": "Ночной дозор", "desc": "Позвал бота ночью"},
    "secret_caps_ping": {"icon": "🔊", "name": "Громкий вызов", "desc": "Позвал бота КАПСОМ"},
}

# Пороги по сообщениям: (порог, achievement_id)
_MSG_THRESHOLDS = [
    (1, "first_msg"), (10, "msg_10"), (25, "msg_25"),
    (50, "msg_50"), (100, "msg_100"), (250, "msg_250"),
    (500, "msg_500"), (1000, "msg_1000"), (2500, "msg_2500"),
    (5000, "msg_5000"), (10000, "msg_10000"),
]

# Пороги по матам
_SWEAR_THRESHOLDS = [
    (1, "first_swear"), (10, "swear_10"), (25, "swear_25"),
    (50, "swear_50"), (100, "swear_100"), (200, "swear_200"),
    (500, "swear_500"),
]

# Пороги по стрику
_STREAK_THRESHOLDS = [
    (3, "streak_3"), (7, "streak_7"), (14, "streak_14"),
    (30, "streak_30"), (60, "streak_60"), (100, "streak_100"),
]


def _normalize_text(text: str) -> str:
    return (text or "").lower().replace("ё", "е").strip()


def _is_mention(text_norm: str, bot_username: str, bot_name: str) -> bool:
    if not text_norm:
        return False
    uname = (bot_username or "").strip().lower()
    bname = (bot_name or "").strip().lower()
    return bool((uname and f"@{uname}" in text_norm) or (bname and bname in text_norm))


def _phrase_secret_ids(text: str, bot_username: str, bot_name: str) -> list[str]:
    text_norm = _normalize_text(text)
    if not text_norm:
        return []

    ids: list[str] = []
    mention = _is_mention(text_norm, bot_username, bot_name)

    if mention and "папочк" in text_norm:
        ids.append("secret_call_dad")

    if mention and (
        "бот лучший" in text_norm
        or "скаут лучший" in text_norm
        or "респект боту" in text_norm
    ):
        ids.append("secret_respect_bot")

    if mention and (
        "проверка связи" in text_norm
        or "ты жив" in text_norm
        or "на связи?" in text_norm
    ):
        ids.append("secret_signal_check")

    now_hour = datetime.datetime.now(_MSK).hour
    if mention and now_hour < 6:
        ids.append("secret_night_ping")

    letters_only = re.sub(r"[^A-Za-zА-Яа-яЁё]", "", text or "")
    if mention and len(letters_only) >= 8 and letters_only.isupper():
        ids.append("secret_caps_ping")

    return ids


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
    bot,
    chat_id: int,
    user_id: int,
    user_name: str,
    msg_count: int,
    swear_count: int,
    text: str = "",
    bot_username: str = "",
    bot_name: str = "",
) -> None:
    """Проверяет ачивки по сообщениям, матам и секретным фразам."""
    for threshold, ach_id in _MSG_THRESHOLDS:
        if msg_count >= threshold and grant_achievement(user_id, chat_id, ach_id):
            await _announce(bot, chat_id, user_name, ach_id)

    for threshold, ach_id in _SWEAR_THRESHOLDS:
        if swear_count >= threshold and grant_achievement(user_id, chat_id, ach_id):
            await _announce(bot, chat_id, user_name, ach_id)

    for ach_id in _phrase_secret_ids(text, bot_username, bot_name):
        if grant_achievement(user_id, chat_id, ach_id):
            await _announce(bot, chat_id, user_name, ach_id)


async def check_streak_achievements(
    bot, chat_id: int, user_id: int, user_name: str, streak: int,
) -> None:
    """Проверяет ачивки по стрику активности."""
    for threshold, ach_id in _STREAK_THRESHOLDS:
        if streak >= threshold and grant_achievement(user_id, chat_id, ach_id):
            await _announce(bot, chat_id, user_name, ach_id)


async def check_unknown_command_achievement(
    bot,
    chat_id: int,
    user_id: int,
    user_name: str,
    command_text: str,
) -> None:
    """Секретная ачивка за неизвестную команду (/какая-то_белиберда)."""
    cmd = (command_text or "").strip()
    if not cmd.startswith("/"):
        return
    if len(cmd) < 3:
        return
    if grant_achievement(user_id, chat_id, "secret_unknown_cmd"):
        await _announce(bot, chat_id, user_name, "secret_unknown_cmd")


async def check_king_achievements(*args, **kwargs) -> None:
    """Устарело: механика короля отключена."""
    return


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
