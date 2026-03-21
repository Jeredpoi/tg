# ==============================================================================
# commands/steam.py — Команда /steam: топ скидок в Steam (CheapShark API)
# ==============================================================================

import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

DEALS_PER_PAGE = 5

SORT_OPTIONS = [
    ("Savings",  "Скидка"),
    ("Rating",   "Рейтинг"),
    ("Price",    "Цена"),
]

CHEAPSHARK_URL = "https://www.cheapshark.com/api/1.0/deals"


async def _fetch_deals(sort_by: str, page: int) -> list:
    params = {
        "storeID": "1",
        "sortBy": sort_by,
        "pageSize": DEALS_PER_PAGE + 1,  # +1 чтобы понять есть ли следующая страница
        "pageNumber": page,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(CHEAPSHARK_URL, params=params)
        resp.raise_for_status()
        return resp.json()


def _build_text(deals: list, sort_by: str, page: int) -> str:
    sort_label = next((label for key, label in SORT_OPTIONS if key == sort_by), sort_by)
    lines = [f"🎮 <b>Скидки в Steam</b>  |  сортировка: {sort_label}\n"]

    for i, deal in enumerate(deals[:DEALS_PER_PAGE], start=1):
        title = deal.get("title", "Неизвестно")
        sale  = deal.get("salePrice", "?")
        orig  = deal.get("normalPrice", "?")
        pct   = int(float(deal.get("savings", 0)))
        rating = deal.get("steamRatingText") or ""

        # Обрезаем длинные названия
        if len(title) > 35:
            title = title[:33] + "…"

        price_line = f"  <s>{orig}$</s> → <b>{sale}$</b>  (-{pct}%)"
        if rating:
            price_line += f"  [{rating}]"

        lines.append(f"{i}. <b>{title}</b>")
        lines.append(price_line)

    return "\n".join(lines)


def _build_keyboard(sort_by: str, page: int, has_next: bool) -> InlineKeyboardMarkup:
    # Строка сортировки
    sort_row = []
    for key, label in SORT_OPTIONS:
        text = f"✅ {label}" if key == sort_by else label
        sort_row.append(InlineKeyboardButton(text, callback_data=f"steam:{key}:0"))

    # Строка навигации
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀", callback_data=f"steam:{sort_by}:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"стр. {page + 1}", callback_data="steam_noop"))
    if has_next:
        nav_row.append(InlineKeyboardButton("▶", callback_data=f"steam:{sort_by}:{page + 1}"))

    return InlineKeyboardMarkup([sort_row, nav_row])


async def steam_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/steam — топ скидок в Steam."""
    msg = await update.message.reply_text("⏳ Загружаю скидки...")

    try:
        deals = await _fetch_deals("Savings", 0)
        has_next = len(deals) > DEALS_PER_PAGE
        text = _build_text(deals, "Savings", 0)
        kb = _build_keyboard("Savings", 0, has_next)
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.exception("steam_command failed: %s", e)
        await msg.edit_text("❌ Не удалось загрузить скидки. Попробуй позже.")


async def steam_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик inline-кнопок /steam."""
    query = update.callback_query

    if query.data == "steam_noop":
        await query.answer()
        return

    # Формат: steam:{sort}:{page}
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer()
        return

    _, sort_by, page_s = parts
    try:
        page = int(page_s)
    except ValueError:
        await query.answer()
        return

    await query.answer()

    try:
        deals = await _fetch_deals(sort_by, page)
        has_next = len(deals) > DEALS_PER_PAGE
        text = _build_text(deals, sort_by, page)
        kb = _build_keyboard(sort_by, page, has_next)
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    except Exception as e:
        logger.exception("steam_callback failed sort=%r page=%d: %s", sort_by, page, e)
        try:
            await query.edit_message_text("❌ Не удалось загрузить скидки. Попробуй позже.")
        except BadRequest:
            pass
