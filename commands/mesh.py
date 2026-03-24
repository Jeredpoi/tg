# ==============================================================================
# commands/mesh.py — Команда /mesh (расписание и ДЗ из МЭШ)
# ==============================================================================

import logging
from datetime import date, timedelta

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import MESH_STUDENT_ID, MESH_TOKEN

logger = logging.getLogger(__name__)

BASE_URL = "https://dnevnik.mos.ru"
DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def _week_monday(offset: int = 0) -> date:
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset)


def _week_label(monday: date) -> str:
    sunday = monday + timedelta(days=6)
    this_monday = _week_monday(0)
    label = f"{monday.strftime('%d.%m')}–{sunday.strftime('%d.%m')}"
    if monday == this_monday:
        label += " (текущая)"
    elif monday == this_monday - timedelta(weeks=1):
        label += " (прошлая)"
    elif monday == this_monday + timedelta(weeks=1):
        label += " (следующая)"
    return label


async def fetch_homeworks(token: str, student_id: int, start: date, end: date) -> dict[str, int]:
    """Возвращает {date_str: кол-во_дз}."""
    headers = {"auth-token": token, "profile-id": str(student_id)}
    params = {
        "student_id": student_id,
        "begin_date": start.strftime("%Y-%m-%d"),
        "end_date":   end.strftime("%Y-%m-%d"),
    }
    async with httpx.AsyncClient(timeout=12) as client:
        r = await client.get(f"{BASE_URL}/api/homeworks", headers=headers, params=params)
        r.raise_for_status()

    result: dict[str, int] = {}
    for hw in r.json():
        d = hw.get("date", "")[:10]
        if d:
            result[d] = result.get(d, 0) + 1
    return result


def _keyboard(offset: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀◀", callback_data=f"mesh_nav:{offset - 1}"),
        InlineKeyboardButton("▶▶", callback_data=f"mesh_nav:{offset + 1}"),
    ]])


async def _render(offset: int, token: str | None = None, student_id: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    t   = token      or MESH_TOKEN
    sid = student_id or MESH_STUDENT_ID
    monday = _week_monday(offset)
    sunday = monday + timedelta(days=6)

    hw = await fetch_homeworks(t, sid, monday, sunday)

    lines = [f"📅 <b>Неделя {_week_label(monday)}</b>\n"]
    for i, day in enumerate(DAYS_RU[:6]):
        d = (monday + timedelta(days=i)).strftime("%Y-%m-%d")
        lines.append(f"{day} ({hw.get(d, 0)})")

    return "\n".join(lines), _keyboard(offset)


async def mesh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("⏳ Загружаю расписание...")
    try:
        text, kb = await _render(0)
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except httpx.HTTPStatusError as e:
        logger.error("МЭШ HTTP %s", e.response.status_code)
        await msg.edit_text("❌ МЭШ вернул ошибку. Проверь токен и student_id в конфиге.")
    except Exception as e:
        logger.error("МЭШ ошибка: %s", e)
        await msg.edit_text("❌ Не удалось получить данные из МЭШ.")


async def mesh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    offset = int(query.data.split(":")[1])
    try:
        text, kb = await _render(offset)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error("МЭШ callback: %s", e)
        await query.edit_message_text("❌ Не удалось получить данные из МЭШ.")
