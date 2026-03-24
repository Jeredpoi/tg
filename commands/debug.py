# ==============================================================================
# commands/debug.py — Команда /debug
# ==============================================================================

import asyncio
import aiohttp
from telegram import Update
from telegram.ext import ContextTypes
from config import YANDEX_WEATHER_KEY, DATABASE_PATH


async def _check_db() -> tuple[bool, str]:
    try:
        import sqlite3
        con = sqlite3.connect(DATABASE_PATH)
        con.execute("SELECT 1")
        con.close()
        return True, "✅ База данных"
    except Exception as e:
        return False, f"❌ База данных ({e})"


async def _check_weather() -> tuple[bool, str]:
    try:
        url = "https://api.weather.yandex.ru/v2/forecast?lat=55.75&lon=37.61&limit=1"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"X-Yandex-API-Key": YANDEX_WEATHER_KEY}, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    return True, "✅ Яндекс.Погода"
                return False, f"❌ Яндекс.Погода (HTTP {r.status})"
    except Exception as e:
        return False, f"❌ Яндекс.Погода ({type(e).__name__})"


async def _check_steam() -> tuple[bool, str]:
    try:
        url = "https://store.steampowered.com/api/featuredcategories?cc=ru&l=russian"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    return True, "✅ Steam API"
                return False, f"❌ Steam API (HTTP {r.status})"
    except Exception as e:
        return False, f"❌ Steam API ({type(e).__name__})"


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    chat    = update.effective_chat
    user    = update.effective_user

    if not message or not chat or not user:
        return

    username_display = f"@{user.username}" if user.username else "—"

    (db_ok, db_txt), (w_ok, w_txt), (s_ok, s_txt) = await asyncio.gather(
        _check_db(), _check_weather(), _check_steam()
    )

    status = "🟢 Все системы работают" if all([db_ok, w_ok, s_ok]) else "🟡 Есть проблемы"

    text = (
        "🛠 <b>Debug информация</b>\n\n"
        f"<b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"<b>Chat type:</b> {chat.type}\n\n"
        f"<b>User ID:</b> <code>{user.id}</code>\n"
        f"<b>Username:</b> {username_display}\n"
        f"<b>First name:</b> {user.first_name}\n\n"
        f"<b>Message ID:</b> <code>{message.message_id}</code>\n\n"
        f"<b>Статус компонентов:</b> {status}\n"
        f"{db_txt}\n"
        f"{w_txt}\n"
        f"{s_txt}"
    )

    await message.reply_text(text, parse_mode="HTML")
