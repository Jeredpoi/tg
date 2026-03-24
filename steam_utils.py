# steam_utils.py — скидки Steam через Search API
import logging
import time

import httpx

logger = logging.getLogger(__name__)

CACHE_TTL   = 600   # 10 минут
FETCH_BATCH = 100   # игр за один запрос к Steam

_cache: dict = {
    "deals":       [],    # все загруженные игры (несортированные)
    "total_api":   0,     # сколько всего скидок на Steam
    "next_offset": 0,     # с какого offset следующий запрос
    "ts":          0.0,
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


async def _fetch_batch(offset: int) -> tuple[int, list]:
    """Один запрос к Steam Search API. Возвращает (total_api, normalized_deals)."""
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        r = await client.get(
            "https://store.steampowered.com/search/results/",
            params={
                "specials": "1",
                "json":     "1",
                "start":    str(offset),
                "count":    str(FETCH_BATCH),
                "cc":       "ru",
                "l":        "russian",
            },
        )
        if r.status_code != 200:
            logger.warning("Steam search HTTP %d", r.status_code)
            return 0, []

        data  = r.json()
        total = int(data.get("total_count", 0))
        items = data.get("items", [])

        normalized = []
        for item in items:
            price    = item.get("price") or {}
            discount = abs(int(price.get("discount_percent", 0)))
            if discount <= 0:
                continue
            normalized.append({
                "id":               int(item.get("appid", 0)),
                "name":             item.get("name", ""),
                "discount_percent": discount,
                "original_price":   price.get("initial", 0),
                "final_price":      price.get("final",   0),
            })

        logger.info("Steam search offset=%d: %d deals (total_api=%d)", offset, len(normalized), total)
        return total, normalized


def _reset_cache() -> None:
    _cache["deals"]       = []
    _cache["total_api"]   = 0
    _cache["next_offset"] = 0
    _cache["ts"]          = time.time()


async def _get_deals() -> list:
    """Возвращает закэшированные игры (грузит первую пачку, если кэш пустой/устарел)."""
    now = time.time()
    if not _cache["deals"] or now - _cache["ts"] > CACHE_TTL:
        _reset_cache()
        total, batch = await _fetch_batch(0)
        _cache["total_api"]   = total
        _cache["deals"]       = batch
        _cache["next_offset"] = FETCH_BATCH

    return _cache["deals"]


async def _load_more_deals() -> tuple[int, int]:
    """Подгружает следующую пачку. Возвращает (len(deals), total_api)."""
    if _cache["total_api"] > 0 and _cache["next_offset"] >= _cache["total_api"]:
        return len(_cache["deals"]), _cache["total_api"]

    total, batch = await _fetch_batch(_cache["next_offset"])
    _cache["total_api"]    = total
    _cache["deals"].extend(batch)
    _cache["next_offset"] += FETCH_BATCH

    return len(_cache["deals"]), total


def _cache_info() -> tuple[int, int]:
    """(загружено, всего в Steam API)."""
    return len(_cache["deals"]), _cache["total_api"]


async def _get_deals_paged(offset: int, count: int) -> tuple[int, list]:
    """Возвращает (total, deals[offset:offset+count]), догружает если нужно."""
    if not _cache["deals"]:
        await _get_deals()
    while offset + count > len(_cache["deals"]) and len(_cache["deals"]) < _cache["total_api"]:
        await _load_more_deals()
    deals = _cache["deals"][offset: offset + count]
    total = _cache["total_api"]
    return total, deals


def _sort_deals(deals: list, sort_by: str) -> list:
    if sort_by == "price":
        return sorted(deals, key=lambda d: d.get("final_price", 0))
    return sorted(deals, key=lambda d: abs(d.get("discount_percent", 0)), reverse=True)
