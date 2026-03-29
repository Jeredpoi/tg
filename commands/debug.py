# ==============================================================================
# commands/debug.py — Команда /debug
# ==============================================================================

import asyncio
import os
import sqlite3
import aiohttp
from telegram import Update, BotCommandScopeAllGroupChats
from telegram.ext import ContextTypes
from config import YANDEX_WEATHER_KEY, DATABASE_PATH, CHAT_ID, WEBAPP_URL
from database import get_connection


async def _check_db() -> tuple[bool, str]:
    try:
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


async def _check_webapp() -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{WEBAPP_URL}/api/gallery", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    return True, "✅ Веб-сервер (галерея)"
                return False, f"❌ Веб-сервер (HTTP {r.status})"
    except Exception as e:
        return False, f"❌ Веб-сервер ({type(e).__name__})"


def _get_chat_stats(chat_id: int) -> dict:
    conn = None
    try:
        conn = get_connection()
        users     = conn.execute("SELECT COUNT(*) FROM user_stats WHERE chat_id=?", (chat_id,)).fetchone()[0]
        messages  = conn.execute("SELECT COALESCE(SUM(msg_count),0) FROM user_stats WHERE chat_id=?", (chat_id,)).fetchone()[0]
        swears    = conn.execute("SELECT COALESCE(SUM(swear_count),0) FROM user_stats WHERE chat_id=?", (chat_id,)).fetchone()[0]
        photos    = conn.execute("SELECT COUNT(*) FROM photo_ratings WHERE chat_id=?", (chat_id,)).fetchone()[0]
        return {"users": users, "messages": messages, "swears": swears, "photos": photos}
    except Exception:
        return {"users": 0, "messages": 0, "swears": 0, "photos": 0}
    finally:
        if conn:
            conn.close()


def _get_all_setup_chats() -> list[int]:
    try:
        import json, os as _os
        path = _os.path.join(_os.path.dirname(__file__), "..", "setup_chats.json")
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    chat    = update.effective_chat
    user    = update.effective_user

    if not message or not chat or not user:
        return

    (db_ok, db_txt), (w_ok, w_txt), (s_ok, s_txt), (wa_ok, wa_txt) = await asyncio.gather(
        _check_db(), _check_weather(), _check_steam(), _check_webapp()
    )

    all_ok = all([db_ok, w_ok, s_ok, wa_ok])
    status = "🟢 Все системы работают" if all_ok else "🟡 Есть проблемы"

    # Права бота в чате
    bot_perms = "—"
    if chat.type in ("group", "supergroup"):
        try:
            member = await context.bot.get_chat_member(chat.id, context.bot.id)
            can_del = getattr(member, "can_delete_messages", False)
            is_admin = member.status in ("administrator", "creator")
            bot_perms = ("✅ Админ" if is_admin else "👤 Участник")
            bot_perms += (", удаление: ✅" if can_del else ", удаление: ❌")
        except Exception:
            bot_perms = "❌ Не удалось получить"

    # Статистика текущего чата
    stats = _get_chat_stats(chat.id)

    # Все инициализированные чаты
    setup_chats = _get_all_setup_chats()
    setup_chats_str = ", ".join(f"<code>{c}</code>" for c in setup_chats) or "нет"

    # Является ли этот чат целевым для /rate
    import config as cfg
    rate_target = "✅ Да (сюда идут фото из /rate)" if cfg.CHAT_ID == chat.id else f"❌ Нет → <code>{cfg.CHAT_ID}</code>"

    # Размер БД на диске
    try:
        db_size = os.path.getsize(DATABASE_PATH)
        db_size_str = f"{db_size / 1024:.1f} КБ"
    except Exception:
        db_size_str = "—"

    # Команды бота
    bot_commands = await context.bot.get_my_commands()
    if not bot_commands:
        bot_commands = await context.bot.get_my_commands(scope=BotCommandScopeAllGroupChats())
    cmds_text = "\n".join(f"  /{cmd.command} — {cmd.description}" for cmd in bot_commands)

    import html as _html
    username_display = f"@{user.username}" if user.username else "—"

    text = (
        "🛠 <b>Debug информация</b>\n\n"

        "👤 <b>Пользователь</b>\n"
        f"  ID: <code>{user.id}</code>\n"
        f"  Username: {username_display}\n"
        f"  Имя: {_html.escape(user.first_name or '')}\n\n"

        "💬 <b>Текущий чат</b>\n"
        f"  ID: <code>{chat.id}</code>\n"
        f"  Тип: {chat.type}\n"
        f"  Название: {_html.escape(chat.title or '—')}\n"
        f"  Бот: {bot_perms}\n"
        f"  /rate сюда: {rate_target}\n\n"

        "📊 <b>Статистика чата</b>\n"
        f"  Участников в БД: {stats['users']}\n"
        f"  Сообщений: {stats['messages']}\n"
        f"  Матов: {stats['swears']}\n"
        f"  Фото/видео: {stats['photos']}\n\n"

        "🌐 <b>Бот</b>\n"
        f"  Инициализирован в чатах: {setup_chats_str}\n"
        f"  БД на диске: {db_size_str}\n"
        f"  Веб-приложение: {WEBAPP_URL}\n\n"

        f"⚙️ <b>Компоненты:</b> {status}\n"
        f"  {db_txt}\n"
        f"  {w_txt}\n"
        f"  {s_txt}\n"
        f"  {wa_txt}\n\n"

        f"<b>Команды:</b>\n{cmds_text}"
    )

    await message.reply_text(text, parse_mode="HTML")
