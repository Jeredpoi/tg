# ==============================================================================
# commands/achievements_cmd.py — /achievements: красивый просмотр ачивок
# ==============================================================================

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from commands.achievements import (
    ACHIEVEMENTS, CAT_EASY, CAT_HARD, CAT_SECRET,
    get_achievements_page,
)
from database import get_user_achievements

logger = logging.getLogger(__name__)

_PER_PAGE = 5

_CAT_LABELS = {
    CAT_EASY:   "🟢 Лёгкие",
    CAT_HARD:   "🔴 Сложные",
    CAT_SECRET: "🔒 Секретные",
}
_CAT_ORDER = [CAT_EASY, CAT_HARD, CAT_SECRET]


def _build_page_text(user_id: int, chat_id: int, category: str, page: int) -> str:
    data = get_achievements_page(user_id, chat_id, category, page, _PER_PAGE)
    items       = data["items"]
    cur_page    = data["page"]
    total_pages = data["total_pages"]
    earned      = data["earned_count"]
    total       = data["total_count"]

    label = _CAT_LABELS.get(category, category)
    lines = [f"<b>{label}</b>  ({earned}/{total})"]
    lines.append(f"Страница {cur_page + 1} из {total_pages}\n")

    for item in items:
        if item["earned"]:
            lines.append(
                f"{item['icon']} <b>{item['name']}</b>\n"
                f"  <i>{item['desc']}</i>"
            )
        elif item["secret"]:
            lines.append(
                f"🔒 <b>???</b>\n"
                f"  <i>{item['hint']}</i>"
            )
        else:
            lines.append(
                f"{item['icon']} {item['name']}\n"
                f"  <i>{item['hint']}</i>"
            )

    return "\n\n".join(lines)


def _build_keyboard(category: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []

    # Кнопки категорий
    cat_row = []
    for cat in _CAT_ORDER:
        label = _CAT_LABELS[cat]
        if cat == category:
            label = f"[ {label} ]"
        cat_row.append(InlineKeyboardButton(label, callback_data=f"ach:{cat}:0"))
    rows.append(cat_row)

    # Навигация по страницам
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀", callback_data=f"ach:{category}:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶", callback_data=f"ach:{category}:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    return InlineKeyboardMarkup(rows)


async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/achievements — просмотр ачивок с пагинацией."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not update.message:
        return

    category = CAT_EASY
    page = 0

    data = get_achievements_page(user.id, chat.id, category, page, _PER_PAGE)
    text = _build_page_text(user.id, chat.id, category, page)
    kb   = _build_keyboard(category, page, data["total_pages"])

    try:
        await update.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        parse_mode="HTML",
        reply_markup=kb,
    )


async def achievements_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий кнопок ачивок: ach:<category>:<page>"""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "ach":
        return

    _, category, page_str = parts
    if category not in _CAT_LABELS:
        return
    try:
        page = int(page_str)
    except ValueError:
        return

    user = query.from_user
    chat = query.message.chat

    data = get_achievements_page(user.id, chat.id, category, page, _PER_PAGE)
    text = _build_page_text(user.id, chat.id, category, page)
    kb   = _build_keyboard(category, data["page"], data["total_pages"])

    try:
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("achievements_callback: не удалось обновить: %s", e)
