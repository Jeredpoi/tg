# ==============================================================================
# commands/steam.py — Команда /steam: топ скидок в Steam (Steam Storefront API)
# ==============================================================================

import logging
import time
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

DEALS_PER_PAGE = 5
CACHE_TTL = 300  # 5 минут

# Кэш: {"deals": [...], "ts": float}
_cache: dict = {}

SORT_OPTIONS = [
    ("discount", "По скидке"),
    ("price",    "По цене"),
]


async def _get_deals() -> list:
    """Загружает скидки из Steam API с кэшированием на 5 минут."""
    now = time.time()
    if _cache.get("deals") and now - _cache.get("ts", 0) < CACHE_TTL:
        return _cache["deals"]

    seen: set[int] = set()
    deals: list = []

    async with httpx.AsyncClient(timeout=10) as client:
        # Основная выборка — все секции featuredcategories
        r1 = await client.get(
            "https://store.steampowered.com/api/featuredcategories/",
            params={"cc": "ru", "l": "russian"},
        )
        r1.raise_for_status()
        data1 = r1.json()

        for section in data1.values():
            if not isinstance(section, dict):
                continue
            for item in section.get("items", []):
                app_id = item.get("id")
                if not app_id or app_id in seen:
                    continue
                if abs(item.get("discount_percent", 0)) > 0 or item.get("discounted"):
                    seen.add(app_id)
                    deals.append(item)

        # Дополнительно — featured (другой набор игр)
        r2 = await client.get(
            "https://store.steampowered.com/api/featured/",
            params={"cc": "ru", "l": "russian"},
        )
        if r2.status_code == 200:
            data2 = r2.json()
            for section_items in (data2.get("featured_win", []), data2.get("large_capsules", [])):
                for item in section_items:
                    app_id = item.get("id")
                    if not app_id or app_id in seen:
                        continue
                    if abs(item.get("discount_percent", 0)) > 0 or item.get("discounted"):
                        seen.add(app_id)
                        deals.append(item)

    logger.info("Steam deals fetched: %d items", len(deals))
    _cache["deals"] = deals
    _cache["ts"] = now
    return deals


def _sort_deals(deals: list, sort_by: str) -> list:
    if sort_by == "price":
        return sorted(deals, key=lambda d: d.get("final_price", 0))
    # по скидке — сортируем по убыванию abs(discount_percent)
    return sorted(deals, key=lambda d: abs(d.get("discount_percent", 0)), reverse=True)


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
