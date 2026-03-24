# steam_utils.py — скидки Steam с несколькими источниками данных
# 1. CheapShark API (бесплатный, без ключа)
# 2. Steam featuredcategories (резерв, RUB)
# 3. Steam Search API (резерв, с защитой от HTML-ответов)
import logging
import time

import httpx

logger = logging.getLogger(__name__)

CACHE_TTL  = 600   # 10 минут
PAGE_SIZE  = 60

_cache: dict = {
    "deals":      [],
    "total":      0,
    "next_page":  0,
    "ts":         0.0,
    "source":     None,  # какой источник сработал
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


# ── Источник 1: CheapShark ────────────────────────────────────────────────

async def _fetch_cheapshark(page: int) -> tuple[int, list]:
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            "https://www.cheapshark.com/api/1.0/deals",
            params={
                "storeID":    "1",
                "sortBy":     "Savings",
                "pageSize":   str(PAGE_SIZE),
                "pageNumber": str(page),
            },
        )
    if r.status_code != 200:
        raise RuntimeError(f"CheapShark HTTP {r.status_code}")

    total_pages = int(r.headers.get("X-Total-Page-Count", 1))
    normalized = []
    for item in r.json():
        try:
            app_id   = int(item.get("steamAppID") or 0)
            discount = round(float(item.get("savings", 0)))
            if discount <= 0 or not app_id:
                continue
            # Цены в центах USD
            normalized.append({
                "id":               app_id,
                "name":             item.get("title", ""),
                "discount_percent": discount,
                "original_price":   round(float(item.get("normalPrice", 0)) * 100),
                "final_price":      round(float(item.get("salePrice",   0)) * 100),
                "currency":         "USD",
            })
        except (ValueError, TypeError):
            continue
    return total_pages * PAGE_SIZE, normalized


# ── Источник 2: Steam featuredcategories (RUB) ────────────────────────────

async def _fetch_featured() -> tuple[int, list]:
    async with httpx.AsyncClient(timeout=8, headers=_HEADERS) as client:
        r = await client.get(
            "https://store.steampowered.com/api/featuredcategories",
            params={"cc": "ru", "l": "russian"},
        )
    if r.status_code != 200:
        raise RuntimeError(f"featuredcategories HTTP {r.status_code}")

    data = r.json()
    items = data.get("specials", {}).get("items", [])
    normalized = []
    for item in items:
        try:
            if not item.get("discounted"):
                continue
            normalized.append({
                "id":               int(item["id"]),
                "name":             item.get("name", ""),
                "discount_percent": int(item.get("discount_percent", 0)),
                "original_price":   int(item.get("original_price", 0)),
                "final_price":      int(item.get("final_price", 0)),
                "currency":         "RUB",
            })
        except (KeyError, ValueError, TypeError):
            continue
    return len(normalized), normalized


# ── Источник 3: Steam Search API (резерв) ─────────────────────────────────

async def _fetch_steam_search(offset: int) -> tuple[int, list]:
    async with httpx.AsyncClient(timeout=8, headers=_HEADERS) as client:
        r = await client.get(
            "https://store.steampowered.com/search/results/",
            params={
                "specials": "1",
                "json":     "1",
                "start":    str(offset),
                "count":    str(PAGE_SIZE),
                "cc":       "ru",
                "l":        "russian",
            },
        )
    if r.status_code != 200:
        raise RuntimeError(f"Steam search HTTP {r.status_code}")
    if "application/json" not in r.headers.get("content-type", ""):
        raise RuntimeError("Steam search вернул HTML (rate limit/block)")

    data  = r.json()
    total = int(data.get("total_count", 0))
    normalized = []
    for item in data.get("items", []):
        try:
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
                "currency":         "RUB",
            })
        except (ValueError, TypeError):
            continue
    return total, normalized


# ── Кэш и публичный интерфейс ─────────────────────────────────────────────

def _reset_cache() -> None:
    _cache["deals"]     = []
    _cache["total"]     = 0
    _cache["next_page"] = 0
    _cache["ts"]        = time.time()
    _cache["source"]    = None


async def _get_deals() -> list:
    now = time.time()
    if _cache["deals"] and now - _cache["ts"] <= CACHE_TTL:
        return _cache["deals"]

    _reset_cache()

    # Пробуем источники по очереди
    for source, fetcher in [
        ("cheapshark",  lambda: _fetch_cheapshark(0)),
        ("featured",    _fetch_featured),
        ("steam_search",lambda: _fetch_steam_search(0)),
    ]:
        try:
            total, batch = await fetcher()
            if batch:
                _cache["total"]     = total
                _cache["deals"]     = batch
                _cache["next_page"] = 1
                _cache["source"]    = source
                logger.info("Steam deals загружены из %s: %d игр", source, len(batch))
                return _cache["deals"]
            logger.warning("%s вернул 0 игр", source)
        except Exception as e:
            logger.warning("%s недоступен: %s", source, e)

    logger.error("Все источники скидок недоступны")
    return []


async def _load_more_deals() -> tuple[int, int]:
    source = _cache.get("source")
    if source != "cheapshark":
        # featured и steam_search не поддерживают постраничную догрузку в том же виде
        return len(_cache["deals"]), _cache["total"]

    max_pages = (_cache["total"] + PAGE_SIZE - 1) // PAGE_SIZE
    if _cache["next_page"] >= max_pages:
        return len(_cache["deals"]), _cache["total"]

    try:
        total, batch = await _fetch_cheapshark(_cache["next_page"])
        _cache["total"]  = total
        _cache["deals"].extend(batch)
        _cache["next_page"] += 1
    except Exception as e:
        logger.warning("CheapShark load_more failed: %s", e)

    return len(_cache["deals"]), _cache["total"]


def _cache_info() -> tuple[int, int]:
    return len(_cache["deals"]), _cache["total"]


async def _get_deals_paged(offset: int, count: int) -> tuple[int, list]:
    if not _cache["deals"]:
        await _get_deals()

    max_pages = (_cache["total"] + PAGE_SIZE - 1) // PAGE_SIZE if _cache["total"] else 1
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
