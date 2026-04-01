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
    "first_msg":      {"icon": "🗣",  "name": "Первый шаг",         "desc": "Написал первое сообщение в чате"},
    "msg_5":          {"icon": "👀",  "name": "Разогрев",           "desc": "5 сообщений"},
    "msg_10":         {"icon": "💬",  "name": "Разговорчивый",      "desc": "10 сообщений"},
    "msg_25":         {"icon": "📝",  "name": "На связи",           "desc": "25 сообщений"},
    "msg_50":         {"icon": "📨",  "name": "Постоянный гость",   "desc": "50 сообщений"},
    "msg_75":         {"icon": "🧩",  "name": "Свой в доску",       "desc": "75 сообщений"},
    "msg_100":        {"icon": "📢",  "name": "Болтун",             "desc": "100 сообщений"},
    "msg_150":        {"icon": "📮",  "name": "Поток текста",       "desc": "150 сообщений"},
    "msg_250":        {"icon": "📡",  "name": "Эфир открыт",        "desc": "250 сообщений"},
    "msg_400":        {"icon": "🎛",  "name": "Частота занята",     "desc": "400 сообщений"},
    "msg_500":        {"icon": "📣",  "name": "Оратор",             "desc": "500 сообщений"},
    "msg_750":        {"icon": "🎚",  "name": "Громкая связь",      "desc": "750 сообщений"},
    "msg_1000":       {"icon": "🎙",  "name": "Легенда чата",       "desc": "1000 сообщений"},
    "msg_1500":       {"icon": "🧠",  "name": "Фабрика мыслей",     "desc": "1500 сообщений"},
    "msg_2500":       {"icon": "🏟",  "name": "Голос канала",       "desc": "2500 сообщений"},
    "msg_4000":       {"icon": "🛸",  "name": "Орбита чата",        "desc": "4000 сообщений"},
    "msg_5000":       {"icon": "🌋",  "name": "Поток сознания",     "desc": "5000 сообщений"},
    "msg_7500":       {"icon": "🚀",  "name": "Сверхзвук",          "desc": "7500 сообщений"},
    "msg_10000":      {"icon": "🛰",  "name": "Архитектор чата",    "desc": "10000 сообщений"},
    "msg_15000":      {"icon": "🌠",  "name": "Космический шум",    "desc": "15000 сообщений"},
    "msg_25000":      {"icon": "🏛",  "name": "Хранитель архива",   "desc": "25000 сообщений"},
    "msg_50000":      {"icon": "👁",  "name": "Вечный онлайн",      "desc": "50000 сообщений"},
    # Секретные по сообщениям/комбо
    "secret_monk_1k": {"icon": "🕯",  "name": "???",                "desc": "Секретная ачивка за редкую дисциплину"},
    "secret_zero_3k": {"icon": "🧊",  "name": "???",                "desc": "Секретная ачивка за невозможную чистоту"},
    "secret_exact_2048_64": {"icon": "🔐", "name": "???",           "desc": "Секретная ачивка за точный баланс"},
    "secret_7777_777": {"icon": "🎰", "name": "???",                "desc": "Секретная ачивка для любителей семёрок"},
    "secret_chaos_4096_1024": {"icon": "🧬", "name": "???",         "desc": "Секретная ачивка за экстремальный режим"},
    # Маты
    "first_swear":     {"icon": "🤬",  "name": "Первый мат",         "desc": "Написал первый мат"},
    "swear_5":         {"icon": "🌶",  "name": "С перчиком",         "desc": "5 матов"},
    "swear_10":        {"icon": "😤",  "name": "Сквернослов",        "desc": "10 матов"},
    "swear_25":        {"icon": "🧨",  "name": "На взводе",          "desc": "25 матов"},
    "swear_50":        {"icon": "💀",  "name": "Матерщинник",        "desc": "50 матов"},
    "swear_75":        {"icon": "⚡",  "name": "Короткий фитиль",    "desc": "75 матов"},
    "swear_100":       {"icon": "⚠️",  "name": "Ругатель",           "desc": "100 матов"},
    "swear_150":       {"icon": "🪓",  "name": "Острый язык",        "desc": "150 матов"},
    "swear_200":       {"icon": "☠️",  "name": "Отец матершины",     "desc": "200 матов"},
    "swear_300":       {"icon": "💥",  "name": "Критический тон",    "desc": "300 матов"},
    "swear_500":       {"icon": "🧱",  "name": "Без фильтра",        "desc": "500 матов"},
    "swear_750":       {"icon": "🪖",  "name": "Штурмовик чата",     "desc": "750 матов"},
    "swear_1000":      {"icon": "🩸",  "name": "Грубая сила",        "desc": "1000 матов"},
    "swear_1500":      {"icon": "🧯",  "name": "Пожар в чате",       "desc": "1500 матов"},
    "swear_2500":      {"icon": "🧨",  "name": "Разносчик бури",     "desc": "2500 матов"},
    "swear_5000":      {"icon": "🌪",  "name": "Катастрофа речи",    "desc": "5000 матов"},
    "secret_swear":    {"icon": "🕳",  "name": "???",                "desc": "Секретная ачивка за предельную резкость"},
    # Стрик активности
    "streak_3":      {"icon": "🔥",  "name": "На волне",            "desc": "3 дня подряд в чате"},
    "streak_7":      {"icon": "⚡",  "name": "Завсегдатай",         "desc": "7 дней подряд в чате"},
    "streak_14":     {"icon": "📆",  "name": "Двухнедельник",       "desc": "14 дней подряд в чате"},
    "streak_21":     {"icon": "⏳",  "name": "Привычка",            "desc": "21 день подряд в чате"},
    "streak_30":     {"icon": "🌟",  "name": "Верный",              "desc": "30 дней подряд в чате"},
    "streak_45":     {"icon": "🧱",  "name": "Режим",               "desc": "45 дней подряд в чате"},
    "streak_60":     {"icon": "🛡",  "name": "Несгибаемый",         "desc": "60 дней подряд в чате"},
    "streak_90":     {"icon": "🗿",  "name": "Монолит",             "desc": "90 дней подряд в чате"},
    "streak_120":    {"icon": "🏯",  "name": "Железный график",     "desc": "120 дней подряд в чате"},
    "streak_180":    {"icon": "🧿",  "name": "Полгода без пропуска","desc": "180 дней подряд в чате"},
    "streak_365":    {"icon": "🏆",  "name": "Календарь закрыт",    "desc": "365 дней подряд в чате"},
    "secret_streak": {"icon": "🌌",  "name": "???",                 "desc": "Секретная ачивка за почти невозможный стрик"},
    # Корона
    "first_king": {"icon": "👑",  "name": "Первый трон",        "desc": "Стал королём дня впервые"},
    "king_5":     {"icon": "👸",  "name": "Постоянный король",  "desc": "5 раз становился королём дня"},
    "king_10":    {"icon": "🤴",  "name": "Династия",           "desc": "10 раз становился королём дня"},
    "king_25":    {"icon": "🦁",  "name": "Император чата",     "desc": "25 раз становился королём дня"},
    "secret_king":{"icon": "♛",  "name": "???",               "desc": "Секретная ачивка за абсолютное доминирование"},
}

# Пороги по сообщениям: (порог, achievement_id)
_MSG_THRESHOLDS = [
    (1, "first_msg"), (5, "msg_5"), (10, "msg_10"),
    (25, "msg_25"), (50, "msg_50"), (75, "msg_75"),
    (100, "msg_100"), (150, "msg_150"), (250, "msg_250"),
    (400, "msg_400"), (500, "msg_500"), (750, "msg_750"),
    (1000, "msg_1000"), (1500, "msg_1500"), (2500, "msg_2500"),
    (4000, "msg_4000"), (5000, "msg_5000"), (7500, "msg_7500"),
    (10000, "msg_10000"), (15000, "msg_15000"),
    (25000, "msg_25000"), (50000, "msg_50000"),
]

# Пороги по матам
_SWEAR_THRESHOLDS = [
    (1, "first_swear"), (5, "swear_5"), (10, "swear_10"),
    (25, "swear_25"), (50, "swear_50"), (75, "swear_75"),
    (100, "swear_100"), (150, "swear_150"), (200, "swear_200"),
    (300, "swear_300"), (500, "swear_500"), (750, "swear_750"),
    (1000, "swear_1000"), (1500, "swear_1500"), (2500, "swear_2500"),
    (5000, "swear_5000"),
]

# Пороги по стрику
_STREAK_THRESHOLDS = [
    (3, "streak_3"), (7, "streak_7"), (14, "streak_14"),
    (21, "streak_21"), (30, "streak_30"), (45, "streak_45"),
    (60, "streak_60"), (90, "streak_90"), (120, "streak_120"),
    (180, "streak_180"), (365, "streak_365"),
]


def _special_message_achievements(msg_count: int, swear_count: int) -> list[str]:
    """Секретные достижения с жёсткими условиями."""
    earned: list[str] = []

    # 1000+ сообщений и почти без матов
    if msg_count >= 1000 and swear_count <= 1:
        earned.append("secret_monk_1k")

    # 3000+ сообщений вообще без матов
    if msg_count >= 3000 and swear_count == 0:
        earned.append("secret_zero_3k")

    # Точный баланс
    if msg_count >= 2048 and swear_count == 64:
        earned.append("secret_exact_2048_64")

    # Режим "семёрок"
    if msg_count >= 7777 and swear_count == 777:
        earned.append("secret_7777_777")

    # Экстремальный хаос
    if msg_count >= 4096 and swear_count >= 1024:
        earned.append("secret_chaos_4096_1024")

    # Старый секрет по грубости речи
    if swear_count >= 1000:
        earned.append("secret_swear")

    return earned


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

    for ach_id in _special_message_achievements(msg_count, swear_count):
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

    if streak >= 180:
        if grant_achievement(user_id, chat_id, "secret_streak"):
            await _announce(bot, chat_id, user_name, "secret_streak")


async def check_king_achievements(
    bot, chat_id: int, user_id: int, user_name: str, king_count: int,
) -> None:
    """Проверяет ачивки за корону (вызывается при назначении короля)."""
    thresholds = [
        (1, "first_king"),
        (5, "king_5"),
        (10, "king_10"),
        (25, "king_25"),
        (50, "secret_king"),
    ]
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
