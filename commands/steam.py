# ==============================================================================
# commands/steam.py — Команда /steam: топ скидок в Steam (Steam Storefront API)
# ==============================================================================

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from steam_utils import _get_deals, _sort_deals

logger = logging.getLogger(__name__)

DEALS_PER_PAGE = 5

SORT_OPTIONS = [
    ("discount", "По скидке"),
    ("price",    "По цене"),
]


def _fmt_price(kopecks) -> str:
    """Копейки → рубли с символом ₽."""
    rubles = int(kopecks) // 100
    return f"{rubles:,}₽".replace(",", " ")


def _build_text(deals: list, sort_by: str, page: int) -> str:
    sort_label = next(l for k, l in SORT_OPTIONS if k == sort_by)
    start = page * DEALS_PER_PAGE
    chunk = deals[start: start + DEALS_PER_PAGE]

    if not deals:
        return "🎮 <b>Скидки в Steam</b>\n\nСейчас скидок не найдено. Попробуй позже."

    lines = [f"🎮 <b>Скидки в Steam</b>  ·  {sort_label}\n"]

    for i, item in enumerate(chunk, start=start + 1):
        app_id   = item.get("id", 0)
        name     = item.get("name", "Неизвестно")
        orig     = item.get("original_price", 0)
        final    = item.get("final_price", 0)
        discount = abs(int(item.get("discount_percent", 0)))
        url      = f"https://store.steampowered.com/app/{app_id}"

        if len(name) > 35:
            name = name[:33] + "…"

        lines.append(
            f'{i}. <a href="{url}"><b>{name}</b></a>\n'
            f'💎 <s>{_fmt_price(orig)}</s> → <b>{_fmt_price(final)}</b>\n'
            f'🔥 Скидка: <b>-{discount}%</b>'
        )

    return "\n\n".join(lines)


def _build_keyboard(sort_by: str, page: int, total: int) -> InlineKeyboardMarkup:
    max_page = max(0, (total - 1) // DEALS_PER_PAGE)

    # Сортировка
    sort_row = [
        InlineKeyboardButton(
            f"✅ {label}" if key == sort_by else label,
            callback_data=f"steam:{key}:0",
        )
        for key, label in SORT_OPTIONS
    ]

    # Навигация
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ Назад", callback_data=f"steam:{sort_by}:{page - 1}"))
    if page < max_page:
        nav_row.append(InlineKeyboardButton("Далее ▶", callback_data=f"steam:{sort_by}:{page + 1}"))

    rows = [sort_row]
    if nav_row:
        rows.append(nav_row)
    return InlineKeyboardMarkup(rows)


async def steam_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/steam — топ скидок в Steam."""
    msg = await update.message.reply_text("⏳ Загружаю скидки...", disable_web_page_preview=True)
    try:
        deals = await _get_deals()
        sorted_deals = _sort_deals(deals, "discount")
        text = _build_text(sorted_deals, "discount", 0)
        kb   = _build_keyboard("discount", 0, len(sorted_deals))
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except Exception as e:
        logger.exception("steam_command failed: %s", e)
        await msg.edit_text("❌ Не удалось загрузить скидки. Попробуй позже.")


async def steam_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик inline-кнопок /steam."""
    query = update.callback_query

    if query.data == "steam_noop":
        await query.answer()
        return

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
        deals = await _get_deals()
        sorted_deals = _sort_deals(deals, sort_by)
        text = _build_text(sorted_deals, sort_by, page)
        kb   = _build_keyboard(sort_by, page, len(sorted_deals))
        try:
            await query.edit_message_text(
                text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    except Exception as e:
        logger.exception("steam_callback failed sort=%r page=%d: %s", sort_by, page, e)
        try:
            await query.edit_message_text("❌ Не удалось загрузить скидки. Попробуй позже.")
        except BadRequest:
            pass
