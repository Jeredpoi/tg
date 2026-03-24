# ==============================================================================
# commands/grades.py — Команда /grades (личные оценки из МЭШ)
# ==============================================================================

import logging
from datetime import date, timedelta

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from database import get_mesh_token, save_mesh_token

logger = logging.getLogger(__name__)

BASE_URL = "https://dnevnik.mos.ru"

# (chat_id, bot_message_id) -> user_id  — ожидаем токен ответом
_pending: dict[tuple[int, int], int] = {}

_HOW_TO_GET_TOKEN = (
    "Как получить токен:\n"
    "1. Зайди на dnevnik.mos.ru\n"
    "2. Открой DevTools → F12 → Console\n"
    "3. Введи: <code>localStorage.getItem('auth_token')</code>\n"
    "4. Скопируй значение без кавычек"
)


async def _validate_and_get_student_id(token: str) -> int | None:
    """Проверяет токен, возвращает student_id или None если токен недействителен."""
    headers = {"auth-token": token}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{BASE_URL}/api/profile", headers=headers)
            if r.status_code != 200:
                return None
            data = r.json()
            # Пробуем вытащить student_id из разных форматов ответа
            if isinstance(data, list) and data:
                return data[0].get("id") or data[0].get("student_id")
            if isinstance(data, dict):
                return (
                    data.get("id")
                    or data.get("student_id")
                    or (data.get("profiles") or [{}])[0].get("id")
                )
    except Exception as e:
        logger.error("МЭШ validate token: %s", e)
    return None


async def _show_grades(update: Update, token: str, student_id: int) -> None:
    msg = await update.message.reply_text("⏳ Загружаю оценки...")
    try:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)

        headers = {"auth-token": token, "profile-id": str(student_id)}
        params = {
            "student_id": student_id,
            "begin_date": monday.strftime("%Y-%m-%d"),
            "end_date":   sunday.strftime("%Y-%m-%d"),
        }
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(f"{BASE_URL}/api/marks", headers=headers, params=params)
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
    intro = {
        "bind":    "🔐 Для просмотра оценок нужно привязать аккаунт МЭШ.",
        "expired": "⏰ Сессия МЭШ истекла. Нужно обновить токен.",
    }.get(reason, "")
    return (
        f"{intro}\n\n"
        "Отправь токен <b>ответом на это сообщение</b>.\n\n"
        f"{_HOW_TO_GET_TOKEN}\n\n"
        "⚠️ Сообщение с токеном будет удалено сразу после получения."
    )


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
    valid_id = await _validate_and_get_student_id(token)
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

    token = msg.text.strip()

    # Сразу удаляем сообщение с токеном
    try:
        await msg.delete()
    except Exception:
        pass

    del _pending[key]

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

    student_id = await _validate_and_get_student_id(token)
    if not student_id:
        await wait_msg.edit_text(
            "❌ Токен недействителен или истёк. "
            "Убедись, что скопировал правильно, и попробуй снова."
        )
        return True

    save_mesh_token(expected_uid, token, student_id)
    await wait_msg.edit_text(
        "✅ Аккаунт МЭШ привязан! Используй /grades для просмотра оценок."
    )
    return True
