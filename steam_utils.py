# steam_utils.py — скидки Steam через CheapShark API
# Docs: https://apidocs.cheapshark.com/
import logging
import time

import httpx

logger = logging.getLogger(__name__)

CACHE_TTL   = 600   # 10 минут
PAGE_SIZE   = 60    # игр за один запрос

_cache: dict = {
    "deals":      [],
    "total":      0,
    "next_page":  0,
    "ts":         0.0,
}

_URL = "https://www.cheapshark.com/api/1.0/deals"


async def _fetch_page(page: int) -> tuple[int, list]:
    """Один запрос к CheapShark. Возвращает (total_approx, normalized_deals)."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(_URL, params={
            "storeID":    "1",        # Steam
            "sortBy":     "Savings",  # сортировка по размеру скидки
            "pageSize":   str(PAGE_SIZE),
            "pageNumber": str(page),
            "onSale":     "1",
        })

    if r.status_code != 200:
        logger.warning("CheapShark HTTP %d", r.status_code)
        return 0, []

    total_pages = int(r.headers.get("X-Total-Page-Count", 1))
    total = total_pages * PAGE_SIZE

    normalized = []
    for item in r.json():
        try:
            app_id   = int(item.get("steamAppID") or 0)
            discount = round(float(item.get("savings", 0)))
            if discount <= 0 or not app_id:
                continue
            # Цены в центах (USD)
            sale   = round(float(item.get("salePrice",   0)) * 100)
            normal = round(float(item.get("normalPrice", 0)) * 100)
            normalized.append({
                "id":               app_id,
                "name":             item.get("title", ""),
                "discount_percent": discount,
                "original_price":   normal,
                "final_price":      sale,
            })
        except (ValueError, TypeError):
            continue

    logger.info("CheapShark page=%d: %d deals (total_pages=%d)", page, len(normalized), total_pages)
    return total, normalized


def _reset_cache() -> None:
    _cache["deals"]     = []
    _cache["total"]     = 0
    _cache["next_page"] = 0
    _cache["ts"]        = time.time()


async def _get_deals() -> list:
    """Возвращает закэшированные игры (грузит первую страницу, если кэш пустой/устарел)."""
    now = time.time()
    if not _cache["deals"] or now - _cache["ts"] > CACHE_TTL:
        _reset_cache()
        total, batch = await _fetch_page(0)
        _cache["total"]     = total
        _cache["deals"]     = batch
        _cache["next_page"] = 1
    return _cache["deals"]


async def _load_more_deals() -> tuple[int, int]:
    """Подгружает следующую страницу. Возвращает (len(deals), total)."""
    max_pages = (_cache["total"] + PAGE_SIZE - 1) // PAGE_SIZE
    if _cache["next_page"] >= max_pages:
        return len(_cache["deals"]), _cache["total"]

    total, batch = await _fetch_page(_cache["next_page"])
    _cache["total"]  = total
    _cache["deals"].extend(batch)
    _cache["next_page"] += 1

    return len(_cache["deals"]), total


def _cache_info() -> tuple[int, int]:
    """(загружено, всего)."""
    return len(_cache["deals"]), _cache["total"]


async def _get_deals_paged(offset: int, count: int) -> tuple[int, list]:
    """Возвращает (total, deals[offset:offset+count]), догружает если нужно."""
    if not _cache["deals"]:
        await _get_deals()

    max_pages = (_cache["total"] + PAGE_SIZE - 1) // PAGE_SIZE
    while offset + count > len(_cache["deals"]) and _cache["next_page"] < max_pages:
        prev = len(_cache["deals"])
        await _load_more_deals()
        if len(_cache["deals"]) == prev:
            break

    deals = _cache["deals"][offset: offset + count]
    all_loaded = _cache["next_page"] >= max_pages
    total = len(_cache["deals"]) if all_loaded else _cache["total"]
    return total, deals


def _sort_deals(deals: list, sort_by: str) -> list:
    if sort_by == "price":
        return sorted(deals, key=lambda d: d.get("final_price", 0))
    return sorted(deals, key=lambda d: d.get("discount_percent", 0), reverse=True)
