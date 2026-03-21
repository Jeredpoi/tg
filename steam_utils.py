# steam_utils.py — функции получения и сортировки скидок Steam (без telegram)
import logging
import time
import httpx

logger = logging.getLogger(__name__)

CACHE_TTL = 300
_cache: dict = {}


async def _get_deals() -> list:
    now = time.time()
    if _cache.get("deals") and now - _cache.get("ts", 0) < CACHE_TTL:
        return _cache["deals"]

    seen: set[int] = set()
    deals: list = []

    async with httpx.AsyncClient(timeout=10) as client:
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
    return sorted(deals, key=lambda d: abs(d.get("discount_percent", 0)), reverse=True)
