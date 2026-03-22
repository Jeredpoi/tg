# steam_utils.py — получение скидок Steam с поддержкой пагинации
import html as _html
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

CACHE_TTL = 300
# Кэш страниц: (offset, count) -> (ts, items, total)
_page_cache: dict = {}


def _parse_search_html(html_content: str) -> list:
    """Парсит HTML выдачи Steam Search и извлекает данные об играх."""
    items = []
    for m in re.finditer(
        r'<a\b[^>]+\bdata-ds-appid="(\d+)"[^>]*>(.*?)</a>',
        html_content,
        re.DOTALL,
    ):
        app_id = int(m.group(1))
        row = m.group(2)

        name_m = re.search(r'<span class="title">([^<]+)</span>', row)
        if not name_m:
            continue
        name = _html.unescape(name_m.group(1).strip())

        disc_m = re.search(r'class="search_discount[^"]*"[^>]*>\s*-?(\d+)%', row)
        discount = int(disc_m.group(1)) if disc_m else 0

        price_m = re.search(r'data-price-final="(\d+)"', row)
        final_price = int(price_m.group(1)) if price_m else 0

        if discount > 0 and final_price > 0:
            original_price = round(final_price * 100 / (100 - discount))
        else:
            original_price = final_price

        items.append({
            "id": app_id,
            "name": name,
            "discount_percent": discount,
            "original_price": original_price,
            "final_price": final_price,
        })
    return items


async def _get_deals_paged(offset: int = 0, count: int = 50) -> tuple[int, list]:
    """Возвращает страницу скидок из Steam Search Specials с кэшированием."""
    key = (offset, count)
    now = time.time()

    if key in _page_cache:
        ts, items, total = _page_cache[key]
        if now - ts < CACHE_TTL:
            return total, items

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://store.steampowered.com/search/results/",
            params={
                "specials": "1",
                "json": "1",
                "cc": "ru",
                "l": "russian",
                "start": str(offset),
                "count": str(count),
            },
        )
        r.raise_for_status()
        data = r.json()

    total = data.get("total_count", 0)
    items = _parse_search_html(data.get("results_html", ""))
    logger.info(
        "Steam specials page: offset=%d count=%d total=%d parsed=%d",
        offset, count, total, len(items),
    )
    _page_cache[key] = (now, items, total)
    return total, items


async def _get_deals() -> list:
    """Обратная совместимость для commands/steam.py."""
    _, items = await _get_deals_paged(0, 50)
    return items


def _sort_deals(deals: list, sort_by: str) -> list:
    if sort_by == "price":
        return sorted(deals, key=lambda d: d.get("final_price", 0))
    return sorted(deals, key=lambda d: abs(d.get("discount_percent", 0)), reverse=True)
