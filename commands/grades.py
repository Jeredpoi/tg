# ==============================================================================
# commands/grades.py — Команда /grades (личные оценки из МЭШ)
# ==============================================================================

import json
import logging
from datetime import date, timedelta

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from database import get_mesh_token, save_mesh_token

logger = logging.getLogger(__name__)

BASE_URL = "https://school.mos.ru"

# (chat_id, bot_message_id) -> user_id  — ожидаем токен ответом
_pending: dict[tuple[int, int], int] = {}

_TOKEN_LINK = "https://school.mos.ru/?backUrl=https%3A%2F%2Fschool.mos.ru%2Fv2%2Ftoken%2Frefresh"

_HOW_TO_GET_TOKEN = (
    "<b>Авторизация в МЭШ</b>\n\n"
    "Для привязки аккаунта нужно:\n"
    f'1. Перейти по <a href="{_TOKEN_LINK}">ссылке</a> и войти в аккаунт\n'
    "2. Скопировать с открывшейся страницы весь текст и отправить сюда"
)


async def _validate_and_get_student_id(token: str) -> tuple[int | None, str]:
    """Возвращает (studentProfileId, error_msg). error_msg пустой если успех."""
    headers = {
        "auth-token":      token,
        "x-mes-subsystem": "familyweb",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BASE_URL}/api/family/mobile/v1/profile",
                headers=headers,
            )
        logger.info("МЭШ profile status=%s body=%s", r.status_code, r.text[:300])
        if r.status_code == 401:
            return None, f"Токен отклонён сервером (401). Получи новый по ссылке."
        if r.status_code == 403:
            return None, f"Доступ запрещён (403). Возможно токен истёк."
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


async def _show_grades(update: Update, token: str, student_id: int) -> None:
    msg = await update.message.reply_text("⏳ Загружаю оценки...")
    try:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)

        headers = {
            "Authorization":    f"Bearer {token}",
            "x-mes-subsystem": "familyweb",
        }
        params = {
            "studentProfileId": student_id,
            "from": monday.strftime("%Y-%m-%d"),
            "to":   sunday.strftime("%Y-%m-%d"),
        }
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(
                f"{BASE_URL}/api/family/mobile/v1/marks",
                headers=headers,
                params=params,
            )
            r.raise_for_status()

        marks = r.json()
        if not marks:
            await msg.edit_text(
                f"📊 <b>Оценки {monday.strftime('%d.%m')}–{sunday.strftime('%d.%m')}</b>\n\n"
                "За эту неделю оценок нет.",
                parse_mode="HTML",
            )
            return

        by_subject: dict[str, list[str]] = {}
        for m in marks:
            subj = m.get("subject_name", "Неизвестно")
            val  = str(m.get("value", "?"))
            by_subject.setdefault(subj, []).append(val)

        lines = [f"📊 <b>Оценки {monday.strftime('%d.%m')}–{sunday.strftime('%d.%m')}</b>\n"]
        for subj in sorted(by_subject):
            vals = by_subject[subj]
            avg  = round(sum(int(v) for v in vals if v.isdigit()) / len(vals), 1)
            lines.append(f"<b>{subj}:</b> {', '.join(vals)}  <i>(ср. {avg})</i>")

        await msg.edit_text("\n".join(lines), parse_mode="HTML")

    except httpx.HTTPStatusError as e:
        logger.error("МЭШ grades HTTP %s", e.response.status_code)
        if e.response.status_code in (401, 403):
            await msg.edit_text("⏰ Сессия истекла. Запусти /grades снова и обнови токен.")
        else:
            await msg.edit_text("❌ Ошибка получения оценок из МЭШ.")
    except Exception as e:
        logger.error("МЭШ grades: %s", e)
        await msg.edit_text("❌ Не удалось получить оценки.")


def _ask_for_token_text(reason: str = "bind") -> str:
    if reason == "expired":
        return f"⏳ Сессия МЭШ истекла, нужно обновить привязку\n\n{_HOW_TO_GET_TOKEN}"
    return _HOW_TO_GET_TOKEN


async def grades_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    row = get_mesh_token(user_id)

    if not row:
        msg = await update.message.reply_text(
            _ask_for_token_text("bind"), parse_mode="HTML"
        )
        _pending[(update.effective_chat.id, msg.message_id)] = user_id
        return

    token, student_id = row

    # Быстрая проверка токена
    valid_id, err = await _validate_and_get_student_id(token)
    if not valid_id:
        msg = await update.message.reply_text(
            _ask_for_token_text("expired"), parse_mode="HTML"
        )
        _pending[(update.effective_chat.id, msg.message_id)] = user_id
        return

    await _show_grades(update, token, student_id or valid_id)


async def handle_token_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Вызывается из общего обработчика текста.
    Если сообщение — ответ на запрос токена, обрабатывает его.
    Возвращает True если обработано (стоп дальнейшая обработка).
    """
    msg = update.message
    if not msg or not msg.reply_to_message or not msg.text:
        return False

    chat_id       = update.effective_chat.id
    reply_to_id   = msg.reply_to_message.message_id
    key           = (chat_id, reply_to_id)

    if key not in _pending:
        return False

    expected_uid = _pending[key]
    if update.effective_user.id != expected_uid:
        return False

    raw = msg.text.strip()

    # Сразу удаляем сообщение с токеном
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
            text="❌ Пустой токен. Запусти /grades снова.",
            reply_to_message_id=reply_to_id,
        )
        return True

    wait_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ Проверяю токен...",
        reply_to_message_id=reply_to_id,
    )

    student_id, err = await _validate_and_get_student_id(token)
    if not student_id:
        await wait_msg.edit_text(f"❌ {err}")
        return True

    save_mesh_token(expected_uid, token, student_id)
    await wait_msg.edit_text(
        "✅ Аккаунт МЭШ привязан! Используй /grades для просмотра оценок."
    )
    return True
