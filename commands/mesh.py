# ==============================================================================
# commands/mesh.py — Команда /mesh (расписание и ДЗ из МЭШ)
# ==============================================================================

import json
import logging
from datetime import date, timedelta

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import get_mesh_token, save_mesh_token

logger = logging.getLogger(__name__)

BASE_URL = "https://school.mos.ru"
DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

_TOKEN_LINK = "https://school.mos.ru/?backUrl=https%3A%2F%2Fschool.mos.ru%2Fv2%2Ftoken%2Frefresh"

# (chat_id, bot_message_id) -> user_id — ожидаем токен ответом
_pending: dict[tuple[int, int], int] = {}


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


async def _validate_and_get_student_id(token: str) -> tuple[int | None, str]:
    """Возвращает (studentProfileId, error_msg). error_msg пустой если успех."""
    headers = {
        "auth-token":      token,
        "x-mes-subsystem": "familyweb",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{BASE_URL}/api/family/mobile/v1/profile", headers=headers)
        logger.info("МЭШ profile status=%s body=%s", r.status_code, r.text[:300])
        if r.status_code == 401:
            return None, "Токен отклонён сервером (401). Получи новый по ссылке."
        if r.status_code == 403:
            return None, "Доступ запрещён (403). Возможно токен истёк."
        if r.status_code != 200:
            return None, f"Сервер МЭШ ответил {r.status_code}. Попробуй позже."
        data = r.json()
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, dict):
            sid = (
                data.get("studentProfileId")
                or data.get("id")
                or (data.get("children") or [{}])[0].get("id")
                or (data.get("profiles") or [{}])[0].get("id")
            )
            if sid:
                return sid, ""
            return None, f"Токен принят, но не удалось найти ID ученика. Ответ: {str(data)[:150]}"
    except Exception as e:
        logger.error("МЭШ validate token: %s", e)
        return None, f"Ошибка соединения: {type(e).__name__}: {e}"
    return None, "Неожиданный формат ответа от МЭШ."


async def fetch_homeworks(token: str, student_id: int, start: date, end: date) -> dict[str, int]:
    """Возвращает {date_str: кол-во_дз}."""
    headers = {
        "auth-token":      token,
        "x-mes-subsystem": "familyweb",
    }
    params = {
        "studentProfileId": student_id,
        "from": start.strftime("%Y-%m-%d"),
        "to":   end.strftime("%Y-%m-%d"),
    }
    async with httpx.AsyncClient(timeout=12) as client:
        r = await client.get(
            f"{BASE_URL}/api/family/mobile/v1/homework/short",
            headers=headers,
            params=params,
        )
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


async def _render(offset: int, token: str, student_id: int) -> tuple[str, InlineKeyboardMarkup]:
    monday = _week_monday(offset)
    sunday = monday + timedelta(days=6)
    hw = await fetch_homeworks(token, student_id, monday, sunday)

    lines = [f"📅 <b>Неделя {_week_label(monday)}</b>\n"]
    for i, day in enumerate(DAYS_RU[:6]):
        d = (monday + timedelta(days=i)).strftime("%Y-%m-%d")
        lines.append(f"{day} ({hw.get(d, 0)})")

    return "\n".join(lines), _keyboard(offset)


_ASK_TOKEN_TEXT = (
    "<b>Авторизация в МЭШ</b>\n\n"
    "Для привязки аккаунта нужно:\n"
    f'1. Перейти по <a href="{_TOKEN_LINK}">ссылке</a> и войти в аккаунт\n'
    "2. Скопировать с открывшейся страницы весь текст и отправить сюда"
)


def _ask_for_token_text(reason: str = "bind") -> str:
    if reason == "expired":
        return f"⏳ Сессия МЭШ истекла, нужно обновить привязку\n\n{_ASK_TOKEN_TEXT}"
    return _ASK_TOKEN_TEXT


async def mesh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    row = get_mesh_token(user_id)

    if not row:
        msg = await update.message.reply_text(
            _ask_for_token_text("bind"), parse_mode="HTML"
        )
        _pending[(update.effective_chat.id, msg.message_id)] = user_id
        return

    token, student_id = row

    valid_id, err = await _validate_and_get_student_id(token)
    if not valid_id:
        msg = await update.message.reply_text(
            _ask_for_token_text("expired"), parse_mode="HTML"
        )
        _pending[(update.effective_chat.id, msg.message_id)] = user_id
        return

    msg = await update.message.reply_text("⏳ Загружаю расписание...")
    try:
        text, kb = await _render(0, token, student_id or valid_id)
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except httpx.HTTPStatusError as e:
        logger.error("МЭШ HTTP %s", e.response.status_code)
        await msg.edit_text("❌ МЭШ вернул ошибку.")
    except Exception as e:
        logger.error("МЭШ ошибка: %s", e)
        await msg.edit_text("❌ Не удалось получить данные из МЭШ.")


async def mesh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    offset = int(query.data.split(":")[1])

    row = get_mesh_token(query.from_user.id)
    if not row:
        await query.edit_message_text("⏰ Токен не найден. Запусти /mesh снова.")
        return

    token, student_id = row
    try:
        text, kb = await _render(offset, token, student_id)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error("МЭШ callback: %s", e)
        await query.edit_message_text("❌ Не удалось получить данные из МЭШ.")


async def handle_token_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Вызывается из общего обработчика текста.
    Если сообщение — ответ на запрос токена, обрабатывает его.
    Возвращает True если обработано.
    """
    msg = update.message
    if not msg or not msg.reply_to_message or not msg.text:
        return False

    chat_id     = update.effective_chat.id
    reply_to_id = msg.reply_to_message.message_id
    key         = (chat_id, reply_to_id)

    if key not in _pending:
        return False

    expected_uid = _pending[key]
    if update.effective_user.id != expected_uid:
        return False

    raw = msg.text.strip()

    try:
        await msg.delete()
    except Exception as e:
        logger.warning("Не удалось удалить сообщение с токеном: %s", e)

    del _pending[key]

    # Страница school.mos.ru отдаёт JSON — вытаскиваем поле token
    try:
        token = json.loads(raw).get("token", raw)
    except (json.JSONDecodeError, AttributeError):
        token = raw

    if not token:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Пустой токен. Запусти /mesh снова.",
        )
        return True

    wait_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ Проверяю токен...",
    )

    student_id, err = await _validate_and_get_student_id(token)
    if not student_id:
        await wait_msg.edit_text(f"❌ {err}")
        return True

    save_mesh_token(expected_uid, token, student_id)
    await wait_msg.edit_text(
        "✅ Аккаунт МЭШ привязан! Используй /mesh для просмотра расписания."
    )
    return True
