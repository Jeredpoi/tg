# steam_utils.py — скидки Steam
# Порядок источников: Steam Search → Steam featured → CheapShark
import logging
import time

import httpx

logger = logging.getLogger(__name__)

CACHE_TTL = 600   # 10 минут
PAGE_SIZE = 60

_cache: dict = {
    "deals":      [],
    "total":      0,
    "next_offset": 0,   # для Steam Search (start=) и CheapShark (page=)
    "ts":         0.0,
    "source":     None,
}

_RATE_CACHE: dict = {"rate": 90.0, "ts": 0.0}
_RATE_TTL = 3600


async def _get_usd_rub() -> float:
    """Курс USD/RUB из ЦБ РФ, кэш 1 час."""
    if time.time() - _RATE_CACHE["ts"] < _RATE_TTL:
        return _RATE_CACHE["rate"]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://www.cbr-xml-daily.ru/daily_json.js")
        rate = float(r.json()["Valute"]["USD"]["Value"])
        _RATE_CACHE["rate"] = rate
        _RATE_CACHE["ts"]   = time.time()
        logger.info("USD/RUB курс: %.2f", rate)
    except Exception as e:
        logger.warning("Курс USD/RUB недоступен: %s, используем %.2f", e, _RATE_CACHE["rate"])
    return _RATE_CACHE["rate"]


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


# ── Источник 1: Steam Search API (RUB, пагинация по start) ───────────────

async def _fetch_steam_search(start: int) -> tuple[int, list]:
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        r = await client.get(
            "https://store.steampowered.com/search/results/",
            params={
                "specials": "1",
                "json":     "1",
                "start":    str(start),
                "count":    str(PAGE_SIZE),
                "cc":       "ru",
                "l":        "russian",
            },
        )
    if r.status_code != 200:
        raise RuntimeError(f"Steam search HTTP {r.status_code}")
    ct = r.headers.get("content-type", "")
    if "application/json" not in ct and "text/javascript" not in ct:
        raise RuntimeError(f"Steam вернул не JSON (content-type: {ct[:60]})")

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
    logger.info("Steam search start=%d: %d игр (total=%d)", start, len(normalized), total)
    return total, normalized


# ── Источник 2: Steam featuredcategories (RUB, ~20 игр) ──────────────────

async def _fetch_featured() -> tuple[int, list]:
    async with httpx.AsyncClient(timeout=8, headers=_HEADERS) as client:
        r = await client.get(
            "https://store.steampowered.com/api/featuredcategories",
            params={"cc": "ru", "l": "russian"},
        )
    if r.status_code != 200:
        raise RuntimeError(f"featuredcategories HTTP {r.status_code}")
    items = r.json().get("specials", {}).get("items", [])
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


# ── Источник 3: CheapShark (USD→RUB, пагинация по page) ──────────────────

async def _fetch_cheapshark(page: int) -> tuple[int, list]:
    usd_rub = await _get_usd_rub()
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
            normalized.append({
                "id":               app_id,
                "name":             item.get("title", ""),
                "discount_percent": discount,
                "original_price":   round(float(item.get("normalPrice", 0)) * usd_rub * 100),
                "final_price":      round(float(item.get("salePrice",   0)) * usd_rub * 100),
                "currency":         "RUB",
            })
        except (ValueError, TypeError):
            continue
    return total_pages * PAGE_SIZE, normalized


async def _search_by_title(title: str) -> list:
    """Поиск по названию — сначала Steam, потом CheapShark."""
    # Steam Search с фильтром по названию
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            r = await client.get(
                "https://store.steampowered.com/search/results/",
                params={
                    "term":     title,
                    "specials": "1",
                    "json":     "1",
                    "count":    "20",
                    "cc":       "ru",
                    "l":        "russian",
                },
            )
        ct = r.headers.get("content-type", "")
        if r.status_code == 200 and ("application/json" in ct or "text/javascript" in ct):
            data = r.json()
            normalized = []
            for item in data.get("items", []):
                try:
                    price    = item.get("price") or {}
                    discount = abs(int(price.get("discount_percent", 0)))
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
            if normalized:
                return normalized
    except Exception as e:
        logger.warning("Steam search по названию не удался: %s", e)

    # Резерв: CheapShark
    try:
        usd_rub = await _get_usd_rub()
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://www.cheapshark.com/api/1.0/deals",
                params={"title": title, "storeID": "1", "pageSize": "20"},
            )
        normalized = []
        for item in r.json():
            try:
                app_id = int(item.get("steamAppID") or 0)
                if not app_id:
                    continue
                normalized.append({
                    "id":               app_id,
                    "name":             item.get("title", ""),
                    "discount_percent": round(float(item.get("savings", 0))),
                    "original_price":   round(float(item.get("normalPrice", 0)) * usd_rub * 100),
                    "final_price":      round(float(item.get("salePrice",   0)) * usd_rub * 100),
                    "currency":         "RUB",
                })
            except (ValueError, TypeError):
                continue
        return normalized
    except Exception as e:
        logger.warning("CheapShark search не удался: %s", e)
    return []


# ── Кэш и публичный интерфейс ─────────────────────────────────────────────

def _reset_cache() -> None:
    _cache["deals"]       = []
    _cache["total"]       = 0
    _cache["next_offset"] = 0
    _cache["ts"]          = time.time()
    _cache["source"]      = None


async def _get_deals() -> list:
    now = time.time()
    if _cache["deals"] and now - _cache["ts"] <= CACHE_TTL:
        return _cache["deals"]

    _reset_cache()

    for source, fetcher in [
        ("steam_search", lambda: _fetch_steam_search(0)),
        ("featured",     _fetch_featured),
        ("cheapshark",   lambda: _fetch_cheapshark(0)),
    ]:
        try:
            total, batch = await fetcher()
            if batch:
                _cache["total"]       = total
                _cache["deals"]       = batch
                _cache["next_offset"] = PAGE_SIZE
                _cache["source"]      = source
                logger.info("Скидки из %s: %d игр", source, len(batch))
                return _cache["deals"]
            logger.warning("%s вернул 0 игр", source)
        except Exception as e:
            logger.warning("%s недоступен: %s", source, e)

    logger.error("Все источники скидок недоступны")
    return []


async def _load_more_deals() -> tuple[int, int]:
    source = _cache.get("source")

    if source == "steam_search":
        if _cache["next_offset"] >= _cache["total"]:
            return len(_cache["deals"]), _cache["total"]
        try:
            total, batch = await _fetch_steam_search(_cache["next_offset"])
            _cache["total"]  = total
            _cache["deals"].extend(batch)
            _cache["next_offset"] += PAGE_SIZE
        except Exception as e:
            logger.warning("Steam search load_more: %s", e)

    elif source == "cheapshark":
        page = _cache["next_offset"] // PAGE_SIZE
        max_pages = (_cache["total"] + PAGE_SIZE - 1) // PAGE_SIZE
        if page >= max_pages:
            return len(_cache["deals"]), _cache["total"]
        try:
            total, batch = await _fetch_cheapshark(page)
            _cache["total"]  = total
            _cache["deals"].extend(batch)
            _cache["next_offset"] += PAGE_SIZE
        except Exception as e:
            logger.warning("CheapShark load_more: %s", e)

    return len(_cache["deals"]), _cache["total"]


def _cache_info() -> tuple[int, int]:
    return len(_cache["deals"]), _cache["total"]


async def _get_deals_paged(offset: int, count: int) -> tuple[int, list]:
    if not _cache["deals"]:
        await _get_deals()

    while offset + count > len(_cache["deals"]) and _cache["next_offset"] < _cache["total"]:
        prev = len(_cache["deals"])
        await _load_more_deals()
        if len(_cache["deals"]) == prev:
            break

    deals = _cache["deals"][offset: offset + count]
    all_loaded = _cache["next_offset"] >= _cache["total"]
    total = len(_cache["deals"]) if all_loaded else _cache["total"]
    return total, deals


def _sort_deals(deals: list, sort_by: str) -> list:
    if sort_by == "price":
        return sorted(deals, key=lambda d: d.get("final_price", 0))
    return sorted(deals, key=lambda d: d.get("discount_percent", 0), reverse=True)
