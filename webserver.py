# ==============================================================================
# webserver.py — Aiohttp API-сервер для Telegram Mini App
# Запускать отдельно: python webserver.py
# ==============================================================================

import asyncio
import logging
import os
import sys

import httpx
from aiohttp import web

sys.path.insert(0, os.path.dirname(__file__))

from config import BOT_TOKEN
from database import get_gallery, get_photo_by_key
from commands.steam import _get_deals, _sort_deals

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── /api/steam ──────────────────────────────────────────────────────────────

async def api_steam(request: web.Request) -> web.Response:
    sort = request.rel_url.query.get("sort", "discount")
    try:
        deals = await _get_deals()
        sorted_deals = _sort_deals(deals, sort)
        result = [
            {
                "id":             item.get("id", 0),
                "name":           item.get("name", ""),
                "original_price": item.get("original_price", 0),
                "final_price":    item.get("final_price", 0),
                "discount":       abs(int(item.get("discount_percent", 0))),
                "cover":  f"https://cdn.akamai.steamstatic.com/steam/apps/{item.get('id', 0)}/header.jpg",
                "url":    f"https://store.steampowered.com/app/{item.get('id', 0)}",
            }
            for item in sorted_deals
        ]
        return web.json_response({"deals": result})
    except Exception as e:
        logger.exception("api_steam error: %s", e)
        return web.json_response({"deals": [], "error": str(e)}, status=500)


# ── /api/gallery ─────────────────────────────────────────────────────────────

async def api_gallery(request: web.Request) -> web.Response:
    try:
        rows = get_gallery(100)
        result = [
            {
                "key":        row["key"],
                "author":     "Анонимно" if row["anonymous"] else (row["author_name"] or "Аноним"),
                "avg_score":  round(row["total_score"] / row["vote_count"], 2) if row["vote_count"] else 0,
                "vote_count": row["vote_count"],
            }
            for row in rows
        ]
        return web.json_response({"photos": result})
    except Exception as e:
        logger.exception("api_gallery error: %s", e)
        return web.json_response({"photos": [], "error": str(e)}, status=500)


# ── /api/photo/{key} — проксируем фото из Telegram ───────────────────────────

async def api_photo(request: web.Request) -> web.Response:
    key = request.match_info["key"]
    row = get_photo_by_key(key)
    if not row or not row["photo_id"]:
        raise web.HTTPNotFound()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                params={"file_id": row["photo_id"]},
            )
            data = r.json()
            if not data.get("ok"):
                raise web.HTTPNotFound()

            file_path = data["result"]["file_path"]
            img = await client.get(
                f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            )
            return web.Response(
                body=img.content,
                content_type=img.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except web.HTTPNotFound:
        raise
    except Exception as e:
        logger.exception("api_photo error key=%s: %s", key, e)
        raise web.HTTPInternalServerError()


# ── App ──────────────────────────────────────────────────────────────────────

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/steam",         api_steam)
    app.router.add_get("/api/gallery",       api_gallery)
    app.router.add_get("/api/photo/{key}",   api_photo)
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=8080)
