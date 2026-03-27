# ==============================================================================
# webserver.py — Aiohttp API-сервер для Telegram Mini App
# Запускать отдельно: python webserver.py
# ==============================================================================

import asyncio
import hashlib
import hmac
import logging
import os
import sys
import time

import httpx
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "photos")

from config import BOT_TOKEN
from database import init_db, get_gallery, get_photo_by_key, get_comments, add_comment, delete_photo_by_key

_bot_username: str = ""


def _verify_telegram_auth(data: dict) -> bool:
    """Проверяет подпись данных Telegram Login Widget."""
    hash_ = data.get("hash", "")
    if not hash_:
        return False
    try:
        if time.time() - int(data.get("auth_date", 0)) > 7 * 86400:
            return False
    except (ValueError, TypeError):
        return False
    check = {k: v for k, v in data.items() if k != "hash"}
    check_str = "\n".join(f"{k}={v}" for k, v in sorted(check.items()))
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed = hmac.new(secret, check_str.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, hash_)


async def _on_startup(app: web.Application) -> None:
    global _bot_username
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as c:
            r = await c.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
            data = r.json()
            if data.get("ok"):
                _bot_username = data["result"]["username"]
                logger.info("Bot username: @%s", _bot_username)
    except Exception as e:
        logger.warning("Не удалось получить username бота: %s", e)

# ── /api/steam ──────────────────────────────────────────────────────────────

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
                "closed":        bool(row["closed"]),
                "media_type":    row["media_type"] if row["media_type"] else "photo",
                "comment_count": row["comment_count"] or 0,
                "created_at":    row["created_at"] or "",
                "author_id":     row["author_id"] if not row["anonymous"] else 0,
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
            "commenter_id":   c["commenter_id"] or 0,
            "commenter_name": c["commenter_name"],
            "text":           c["text"],
            "created_at":     c["created_at"],
        }
        for c in comments
    ]
    return web.json_response({"comments": result})


async def api_delete_photo(request: web.Request) -> web.Response:
    key = request.match_info["key"]
    # Требуем Telegram auth в теле запроса
    try:
        body = await request.json()
        tg_auth = body.get("tg_auth") if isinstance(body, dict) else None
    except Exception:
        raise web.HTTPBadRequest()
    if not tg_auth or not isinstance(tg_auth, dict) or not _verify_telegram_auth(tg_auth):
        raise web.HTTPForbidden()
    try:
        uid = int(tg_auth.get("id", 0))
    except (ValueError, TypeError):
        raise web.HTTPForbidden()
    if not uid:
        raise web.HTTPForbidden()

    ok, _, media_type = delete_photo_by_key(key, uid)
    if not ok:
        raise web.HTTPForbidden()

    # Удаляем файл с диска
    ext = "mp4" if media_type == "video" else "jpg"
    fpath = os.path.join(PHOTOS_DIR, f"{key}.{ext}")
    try:
        if os.path.exists(fpath):
            os.remove(fpath)
    except OSError as e:
        logger.warning("api_delete_photo: не удалось удалить файл %s: %s", fpath, e)

    return web.json_response({"ok": True})


async def api_config(request: web.Request) -> web.Response:
    return web.json_response({"bot_username": _bot_username})


async def api_post_comment(request: web.Request) -> web.Response:
    key = request.match_info["key"]
    row = get_photo_by_key(key)
    if not row:
        raise web.HTTPNotFound()
    try:
        body = await request.json()
        text = str(body.get("text", "")).strip()
        tg_auth = body.get("tg_auth")
    except Exception:
        raise web.HTTPBadRequest()
    if not text or len(text) > 500:
        raise web.HTTPBadRequest()

    # Если пришли верифицированные данные Telegram — используем реальное имя
    if tg_auth and isinstance(tg_auth, dict) and _verify_telegram_auth(tg_auth):
        uname = tg_auth.get("username", "")
        commenter_name = f"@{uname}" if uname else tg_auth.get("first_name", "Аноним")
        commenter_id = int(tg_auth.get("id", 0))
    else:
        commenter_name = str(body.get("commenter_name", "Аноним")).strip() or "Аноним"
        try:
            commenter_id = int(body.get("commenter_id", 0))
        except (ValueError, TypeError):
            commenter_id = 0
    commenter_name = commenter_name[:100]

    add_comment(row["photo_id"], commenter_id, commenter_name, text)
    return web.json_response({"ok": True})


# ── /api/photo/{key} — отдаём фото/видео (диск → Telegram API) ──────────────

async def api_photo(request: web.Request) -> web.Response:
    key = request.match_info["key"]
    row = get_photo_by_key(key)
    if not row or not row["photo_id"]:
        raise web.HTTPNotFound()

    media_type = row["media_type"] or "photo"
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


# ── /api/debug/tg — диагностика доступа к Telegram API ──────────────────────

async def api_debug_tg(request: web.Request) -> web.Response:
    results = {}
    for trust in (True, False):
        label = "trust_env=True" if trust else "trust_env=False"
        try:
            async with httpx.AsyncClient(timeout=8, trust_env=trust) as c:
                r = await c.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
                results[label] = {"status": r.status_code, "ok": r.json().get("ok")}
        except Exception as e:
            results[label] = {"error": type(e).__name__, "detail": str(e)}
    return web.json_response(results)


# ── /api/avatar/{user_id} ────────────────────────────────────────────────────

AVATARS_DIR = os.path.join(os.path.dirname(__file__), "photos", "avatars")
AVATAR_TTL  = 24 * 3600  # обновлять не чаще раза в сутки

async def api_avatar(request: web.Request) -> web.Response:
    try:
        user_id = int(request.match_info["user_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest()

    os.makedirs(AVATARS_DIR, exist_ok=True)
    cache_path = os.path.join(AVATARS_DIR, f"{user_id}.jpg")

    # Отдаём кэш если свежий (race condition guard: файл мог удалиться между exists и getmtime)
    try:
        if os.path.exists(cache_path):
            mtime = os.path.getmtime(cache_path)
            if (time.time() - mtime) < AVATAR_TTL:
                return web.FileResponse(cache_path, headers={"Cache-Control": "public, max-age=3600"})
    except OSError:
        pass  # файл исчез между exists() и getmtime() — идём дальше к перезагрузке

    # Запрашиваем у Telegram
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=False) as c:
            r = await c.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos",
                params={"user_id": user_id, "limit": 1},
            )
            data = r.json()
            result = data.get("result") or {}
            if not data.get("ok") or not result.get("total_count"):
                raise web.HTTPNotFound()
            photos = result.get("photos") or []
            if not photos:
                raise web.HTTPNotFound()
            file_id = photos[0][-1]["file_id"]

            r2 = await c.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                params={"file_id": file_id},
            )
            fp = (r2.json().get("result") or {}).get("file_path")
            if not fp:
                raise web.HTTPNotFound()

            r3 = await c.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}")
            r3.raise_for_status()
            with open(cache_path, "wb") as f:
                f.write(r3.content)
    except web.HTTPException:
        # Если есть хоть stale-кэш — отдаём его вместо 404
        if os.path.exists(cache_path):
            return web.FileResponse(cache_path, headers={"Cache-Control": "no-cache"})
        raise
    except Exception as e:
        logger.warning("avatar fetch failed uid=%s: %s", user_id, e)
        if os.path.exists(cache_path):
            return web.FileResponse(cache_path, headers={"Cache-Control": "no-cache"})
        raise web.HTTPNotFound()

    return web.FileResponse(cache_path, headers={"Cache-Control": "public, max-age=3600"})


# ── App ──────────────────────────────────────────────────────────────────────

def create_app() -> web.Application:
    init_db()
    app = web.Application()
    app.router.add_get("/api/config",             api_config)
    app.router.add_get("/api/gallery",            api_gallery)
    app.router.add_get("/api/photo/{key}",        api_photo)
    app.router.add_get("/api/comments/{key}",     api_get_comments)
    app.router.add_post("/api/comments/{key}",    api_post_comment)
    app.router.add_delete("/api/photo/{key}",     api_delete_photo)
    app.router.add_get("/api/avatar/{user_id}",   api_avatar)
    app.router.add_get("/api/debug/tg",           api_debug_tg)
    app.on_startup.append(_on_startup)
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=8080)
