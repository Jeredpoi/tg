# steam_utils.py — получение скидок Steam с поддержкой пагинации
import html as _html
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

CACHE_TTL = 300
_page_cache: dict = {}
_fallback_cache: dict = {}

# Браузерные заголовки для обхода блокировок Steam
_STEAM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://store.steampowered.com/",
}


def _parse_search_html(html_content: str) -> list:
    """Парсит HTML Steam Search и извлекает данные об играх."""
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


async def _try_search_api(offset: int, count: int, trust_env: bool) -> tuple[int, list]:
    """Одна попытка запроса к Steam Search API."""
    async with httpx.AsyncClient(timeout=12, trust_env=trust_env, headers=_STEAM_HEADERS) as client:
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
    return total, items


async def _fetch_via_search_api(offset: int, count: int) -> tuple[int, list]:
    """Пробует Steam Search через прокси, потом напрямую."""
    # Сначала через прокси (если настроен)
    try:
        total, items = await _try_search_api(offset, count, trust_env=True)
        if items:
            logger.info("Steam search (proxy): offset=%d parsed=%d total=%d", offset, len(items), total)
            return total, items
    except Exception as e:
        logger.debug("Steam search (proxy) failed: %s", e)

    # Без прокси (прямое соединение)
    total, items = await _try_search_api(offset, count, trust_env=False)
    logger.info("Steam search (direct): offset=%d parsed=%d total=%d", offset, len(items), total)
    return total, items


def _extract_discounted(data: dict, seen: set) -> list:
    """Извлекает скидки из ответа featuredcategories."""
    result = []
    for section in data.values():
        if not isinstance(section, dict):
            continue
        for item in section.get("items", []):
            app_id = item.get("id")
            if not app_id or app_id in seen:
                continue
            if abs(item.get("discount_percent", 0)) > 0 or item.get("discounted"):
                seen.add(app_id)
                result.append(item)
    return result


async def _fetch_via_featured_apis() -> tuple[int, list]:
    """Собирает скидки из featuredcategories (nPage 1-5) + featured (стабильный fallback)."""
    seen: set[int] = set()
    deals: list = []

    async with httpx.AsyncClient(timeout=15, headers=_STEAM_HEADERS) as client:
        # Параллельно запрашиваем 5 страниц featuredcategories
        tasks = [
            client.get(
                "https://store.steampowered.com/api/featuredcategories/",
                params={"cc": "ru", "l": "russian", "nPage": str(n)},
            )
            for n in range(1, 6)
        ]
        import asyncio as _asyncio
        responses = await _asyncio.gather(*tasks, return_exceptions=True)

        for r in responses:
            if isinstance(r, Exception):
                continue
            try:
                if r.status_code == 200:
                    deals.extend(_extract_discounted(r.json(), seen))
            except Exception:
                continue

        # featured_win + large_capsules
        try:
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
        except Exception:
            pass

    # Нормализуем поля
    normalized = [
        {
            "id": item.get("id", 0),
            "name": item.get("name", ""),
            "discount_percent": abs(item.get("discount_percent", 0)),
            "original_price": item.get("original_price", 0),
            "final_price": item.get("final_price", 0),
        }
        for item in deals
    ]
    logger.info("Steam featured APIs (fallback): %d deals from %d pages", len(normalized), 5)
    return len(normalized), normalized


async def _get_fallback_deals() -> tuple[int, list]:
    """Возвращает fallback-скидки с кэшированием."""
    now = time.time()
    if _fallback_cache.get("deals") and now - _fallback_cache.get("ts", 0) < CACHE_TTL:
        items = _fallback_cache["deals"]
        return len(items), items
    total, items = await _fetch_via_featured_apis()
    _fallback_cache["deals"] = items
    _fallback_cache["ts"] = now
    return total, items


async def _get_deals_paged(offset: int = 0, count: int = 50) -> tuple[int, list]:
    """Возвращает страницу скидок с кэшированием.
    Пробует Steam Search → при неудаче переходит на featured APIs.
    """
    key = (offset, count)
    now = time.time()

    if key in _page_cache:
        ts, items, total = _page_cache[key]
        if now - ts < CACHE_TTL:
            return total, items

    try:
        total, items = await _fetch_via_search_api(offset, count)
        if items:
            _page_cache[key] = (now, items, total)
            return total, items
        logger.warning("Steam search returned 0 items, falling back")
    except Exception as e:
        logger.warning("Steam search unavailable: %s — using fallback", e)

    total, all_deals = await _get_fallback_deals()
    page_items = all_deals[offset: offset + count]
    _page_cache[key] = (now, page_items, total)
    return total, page_items


async def _get_deals() -> list:
    """Обратная совместимость для commands/steam.py."""
    _, items = await _get_deals_paged(0, 50)
    return items


def _sort_deals(deals: list, sort_by: str) -> list:
    if sort_by == "price":
        return sorted(deals, key=lambda d: d.get("final_price", 0))
    return sorted(deals, key=lambda d: abs(d.get("discount_percent", 0)), reverse=True)
