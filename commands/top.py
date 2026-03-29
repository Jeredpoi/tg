# ==============================================================================
# commands/top.py — Команда /top со статистикой чата
# ==============================================================================

import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from database import get_top_messages, get_top_swears, get_gallery

MEDALS = ["🥇", "🥈", "🥉"]


def _medal(i: int) -> str:
    return MEDALS[i] if i < len(MEDALS) else f"{i + 1}."


def _build_messages_text(rows: list) -> str:
    if not rows:
        return "Пока нет данных 😴"
    lines = ["📊 <b>Статистика чата</b>\n", "<b>Топ по сообщениям:</b>\n"]
    for i, row in enumerate(rows):
        name = html.escape(row["first_name"] or row["username"] or "Аноним")
        lines.append(f"{_medal(i)} {name} — {row['msg_count']} сообщений")
    return "\n".join(lines)


def _build_swears_text(rows: list) -> str:
    if not rows:
        return "Пока нет данных 😴"
    lines = ["🤬 <b>Статистика чата</b>\n", "<b>Кто больше матерится:</b>\n"]
    for i, row in enumerate(rows):
        name = html.escape(row["first_name"] or row["username"] or "Аноним")
        lines.append(f"{_medal(i)} {name} — {row['swear_count']} раз(а)")
    return "\n".join(lines)


def _build_rating_text(rows: list) -> str:
    if not rows:
        return "🏆 <b>Рейтинг /rate</b>\n\nПока нет оценённых фото или видео 😴"
    lines = ["🏆 <b>Рейтинг /rate</b>\n", "<b>Топ по средней оценке:</b>\n"]
    for i, row in enumerate(rows):
        avg = round(row["total_score"] / row["vote_count"], 1) if row["vote_count"] > 0 else 0
        author = "Аноним" if row["anonymous"] else html.escape(row["author_name"] or "Аноним")
        lines.append(f"{_medal(i)} {author} — ⭐ {avg} ({row['vote_count']} голос(ов))")
    return "\n".join(lines)


def _get_keyboard(active: str) -> InlineKeyboardMarkup:
    def btn(key, label):
        text = f"✅ {label}" if active == key else label
        return InlineKeyboardButton(text, callback_data=f"top_{key}")

    return InlineKeyboardMarkup([[
        btn("messages", "Сообщения"),
        btn("swears",   "Маты"),
        btn("rating",   "🏆 Рейтинг"),
    ]])


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает топ по сообщениям для текущего чата."""
    chat_id = update.effective_chat.id
    rows = get_top_messages(chat_id)
    text = _build_messages_text(rows)
    keyboard = _get_keyboard("messages")
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def top_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline-кнопки статистики."""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest:
        return

    chat_id = query.message.chat_id

    if query.data == "top_messages":
        rows = get_top_messages(chat_id)
        text = _build_messages_text(rows)
        keyboard = _get_keyboard("messages")
    elif query.data == "top_swears":
        rows = get_top_swears(chat_id)
        text = _build_swears_text(rows)
        keyboard = _get_keyboard("swears")
    elif query.data == "top_rating":
        rows = get_gallery(limit=10, chat_id=chat_id, exclude_anonymous=True)
        text = _build_rating_text(rows)
        keyboard = _get_keyboard("rating")
    else:
        return

    try:
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard)
    except BadRequest:
        pass
