# ==============================================================================
# commands/top.py — Команда /top со статистикой чата
# ==============================================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from database import get_top_messages, get_top_swears


def _build_messages_text(rows: list) -> str:
    """Формирует текст топа по сообщениям."""
    if not rows:
        return "Пока нет данных 😴"

    lines = ["📊 <b>Статистика чата</b>\n", "<b>Топ по сообщениям:</b>\n"]
    for i, row in enumerate(rows, start=1):
        name = row["first_name"] or row["username"] or "Аноним"
        lines.append(f"{i}. {name} — {row['msg_count']} сообщений")
    return "\n".join(lines)


def _build_swears_text(rows: list) -> str:
    """Формирует текст топа по матам."""
    if not rows:
        return "Пока нет данных 😴"

    lines = ["🤬 <b>Статистика чата</b>\n", "<b>Кто больше матерится:</b>\n"]
    for i, row in enumerate(rows, start=1):
        name = row["first_name"] or row["username"] or "Аноним"
        lines.append(f"{i}. {name} — {row['swear_count']} раз(а)")
    return "\n".join(lines)


def _get_keyboard(active: str) -> InlineKeyboardMarkup:
    """
    Возвращает inline-клавиатуру с кнопками переключения статистики.
    active — текущая активная вкладка: 'messages' или 'swears'
    """
    buttons = [
        InlineKeyboardButton(
            text="✅ Сообщения" if active == "messages" else "Сообщения",
            callback_data="top_messages",
        ),
        InlineKeyboardButton(
            text="✅ Маты" if active == "swears" else "Кто матерится",
            callback_data="top_swears",
        ),
    ]
    return InlineKeyboardMarkup([buttons])


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /top. Показывает топ по сообщениям."""
    rows = get_top_messages()
    text = _build_messages_text(rows)
    keyboard = _get_keyboard("messages")

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def top_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline-кнопки статистики."""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest:
        return  # Запрос устарел (бот перезапускался)

    if query.data == "top_messages":
        rows = get_top_messages()
        text = _build_messages_text(rows)
        keyboard = _get_keyboard("messages")
    elif query.data == "top_swears":
        rows = get_top_swears()
        text = _build_swears_text(rows)
        keyboard = _get_keyboard("swears")
    else:
        return

    try:
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard)
    except BadRequest:
        pass  # Сообщение не изменилось — игнорируем
