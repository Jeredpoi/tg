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

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "photos")

from config import BOT_TOKEN
from database import init_db, get_gallery, get_photo_by_key, get_comments, add_comment
from steam_utils import _get_deals, _sort_deals, _get_deals_paged

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── /api/steam ──────────────────────────────────────────────────────────────

async def api_steam(request: web.Request) -> web.Response:
    try:
        offset = max(0, int(request.rel_url.query.get("offset", 0)))
        count  = min(100, max(1, int(request.rel_url.query.get("count", 50))))
    except (ValueError, TypeError):
        offset, count = 0, 50

    try:
        total, deals = await _get_deals_paged(offset, count)
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
            for item in deals
        ]
        return web.json_response({"deals": result, "total": total, "offset": offset})
    except Exception as e:
        logger.exception("api_steam error: %s", e)
        return web.json_response({"deals": [], "total": 0, "offset": offset, "error": str(e)}, status=500)


# ── /api/gallery ─────────────────────────────────────────────────────────────

async def api_gallery(request: web.Request) -> web.Response:
    try:
        chat_id_raw = request.rel_url.query.get("chat_id")
        chat_id = int(chat_id_raw) if chat_id_raw else None
        sort = request.rel_url.query.get("sort", "score")
        rows = get_gallery(100, chat_id=chat_id, sort=sort)
        result = [
            {
                "key":           row["key"],
                "author":        "Анонимно" if row["anonymous"] else (row["author_name"] or "Аноним"),
                "avg_score":     round(row["total_score"] / row["vote_count"], 2) if row["vote_count"] else 0,
                "vote_count":    row["vote_count"],
                "media_type":    row["media_type"] if row["media_type"] else "photo",
                "comment_count": row["comment_count"] or 0,
            }
            for row in rows
        ]
        return web.json_response({"photos": result})
    except Exception as e:
        logger.exception("api_gallery error: %s", e)
        return web.json_response({"photos": [], "error": str(e)}, status=500)


# ── /api/comments/{key} ──────────────────────────────────────────────────────

async def api_get_comments(request: web.Request) -> web.Response:
    key = request.match_info["key"]
    row = get_photo_by_key(key)
    if not row:
        raise web.HTTPNotFound()
    comments = get_comments(row["photo_id"])
    result = [
        {
            "id":             c["id"],
            "commenter_name": c["commenter_name"],
            "text":           c["text"],
            "created_at":     c["created_at"],
        }
        for c in comments
    ]
    return web.json_response({"comments": result})


async def api_post_comment(request: web.Request) -> web.Response:
    key = request.match_info["key"]
    row = get_photo_by_key(key)
    if not row:
        raise web.HTTPNotFound()
    try:
        body = await request.json()
        text = str(body.get("text", "")).strip()
        commenter_name = str(body.get("commenter_name", "Аноним")).strip() or "Аноним"
        commenter_id = int(body.get("commenter_id", 0))
    except Exception:
        raise web.HTTPBadRequest()
    if not text or len(text) > 500:
        raise web.HTTPBadRequest()
    add_comment(row["photo_id"], commenter_id, commenter_name, text)
    return web.json_response({"ok": True})


# ── /api/photo/{key} — отдаём фото/видео (диск → Telegram API) ──────────────

async def api_photo(request: web.Request) -> web.Response:
    key = request.match_info["key"]
    row = get_photo_by_key(key)
    if not row or not row["photo_id"]:
        raise web.HTTPNotFound()

    media_type = row.get("media_type") or "photo"
    is_video = media_type == "video"
    default_ct = "video/mp4" if is_video else "image/jpeg"
    ext = "mp4" if is_video else "jpg"

    # 1. Отдаём с диска (бот скачивает туда при публикации)
    disk_path = os.path.join(PHOTOS_DIR, f"{key}.{ext}")
    if os.path.exists(disk_path):
        resp_headers = {
            "Cache-Control": "public, max-age=86400",
            "Accept-Ranges": "bytes",
        }
        return web.FileResponse(disk_path, headers=resp_headers)

    # 2. Fallback: Telegram API (работает если вебсервер имеет доступ к Telegram)
    logger.warning("api_photo: файл %s не найден на диске, пробуем Telegram API", disk_path)
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            r = await client.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                params={"file_id": row["photo_id"]},
            )
            data = r.json()
            if not data.get("ok"):
                logger.error("api_photo: Telegram getFile вернул ok=false: %s", data)
                raise web.HTTPNotFound()
            file_path = data["result"]["file_path"]

        tg_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        upstream_headers = {}
        if is_video and "Range" in request.headers:
            upstream_headers["Range"] = request.headers["Range"]

        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            upstream = await client.get(tg_url, headers=upstream_headers)

        resp_headers = {"Cache-Control": "public, max-age=3600", "Accept-Ranges": "bytes"}
        for h in ("Content-Range", "Content-Length"):
            if h in upstream.headers:
                resp_headers[h] = upstream.headers[h]

        return web.Response(
            status=upstream.status_code,
            body=upstream.content,
            content_type=upstream.headers.get("content-type", default_ct),
            headers=resp_headers,
        )
    except web.HTTPNotFound:
        raise
    except Exception as e:
        logger.exception("api_photo error key=%s: %s", key, e)
        raise web.HTTPInternalServerError()


# ── App ──────────────────────────────────────────────────────────────────────

def create_app() -> web.Application:
    init_db()
    app = web.Application()
    app.router.add_get("/api/steam",              api_steam)
    app.router.add_get("/api/gallery",            api_gallery)
    app.router.add_get("/api/photo/{key}",        api_photo)
    app.router.add_get("/api/comments/{key}",     api_get_comments)
    app.router.add_post("/api/comments/{key}",    api_post_comment)
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=8080)
