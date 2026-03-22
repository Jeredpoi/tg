# steam_utils.py — скидки Steam, простой и лёгкий
import logging
import time

import httpx

logger = logging.getLogger(__name__)

CACHE_TTL = 600  # 10 минут

_cache: dict = {}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


async def _fetch_deals() -> tuple[int, list]:
    """Один запрос featuredcategories + один featured. Быстро и надёжно."""
    seen: set[int] = set()
    deals: list = []

    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        r1 = await client.get(
            "https://store.steampowered.com/api/featuredcategories/",
            params={"cc": "ru", "l": "russian"},
        )
        if r1.status_code == 200:
            for section in r1.json().values():
                if not isinstance(section, dict):
                    continue
                for item in section.get("items", []):
                    app_id = item.get("id")
                    if app_id and app_id not in seen and abs(item.get("discount_percent", 0)) > 0:
                        seen.add(app_id)
                        deals.append(item)

        r2 = await client.get(
            "https://store.steampowered.com/api/featured/",
            params={"cc": "ru", "l": "russian"},
        )
        if r2.status_code == 200:
            data2 = r2.json()
            for items in (data2.get("featured_win", []), data2.get("large_capsules", [])):
                for item in items:
                    app_id = item.get("id")
                    if app_id and app_id not in seen and abs(item.get("discount_percent", 0)) > 0:
                        seen.add(app_id)
                        deals.append(item)

    normalized = [
        {
            "id": d.get("id", 0),
            "name": d.get("name", ""),
            "discount_percent": abs(d.get("discount_percent", 0)),
            "original_price": d.get("original_price", 0),
            "final_price": d.get("final_price", 0),
        }
        for d in deals
    ]
    logger.info("Steam: получено %d скидок", len(normalized))
    return len(normalized), normalized


async def _get_deals_paged(offset: int = 0, count: int = 50) -> tuple[int, list]:
    now = time.time()
    if _cache.get("deals") and now - _cache.get("ts", 0) < CACHE_TTL:
        all_deals = _cache["deals"]
        total = _cache["total"]
    else:
        total, all_deals = await _fetch_deals()
        _cache["deals"] = all_deals
        _cache["total"] = total
        _cache["ts"] = now

    return total, all_deals[offset: offset + count]


async def _get_deals() -> list:
    _, items = await _get_deals_paged(0, 50)
    return items


def _sort_deals(deals: list, sort_by: str) -> list:
    if sort_by == "price":
        return sorted(deals, key=lambda d: d.get("final_price", 0))
    return sorted(deals, key=lambda d: abs(d.get("discount_percent", 0)), reverse=True)
