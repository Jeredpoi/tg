# ==============================================================================
# commands/dashboard.py — Центр мониторинга и управления (монитор-группа)
# ==============================================================================

import datetime
import json
import logging
import os
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from chat_config import get_monitor_chat_id
from commands.maintenance import is_maintenance, set_maintenance
from database import get_all_users, get_gallery, get_daily_swear_report

logger = logging.getLogger(__name__)

_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "dashboard_state.json")
_BOT_START_TIME = time.time()

# Интервал авто-обновления (секунды)
DASHBOARD_UPDATE_INTERVAL = 300  # 5 минут


# ── Хранение ID сообщений ─────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_dashboard_state() -> dict:
    return _load_state()


# ── Системные метрики ─────────────────────────────────────────────────────────

def _get_server_stats() -> dict:
    stats = {}
    # CPU — /proc/loadavg
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        stats["load1"] = float(parts[0])
        stats["load5"] = float(parts[1])
        stats["load15"] = float(parts[2])
    except Exception:
        stats["load1"] = stats["load5"] = stats["load15"] = 0.0

    # RAM — /proc/meminfo
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                mem[k.strip()] = int(v.split()[0])
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", 0)
        used  = total - avail
        stats["ram_total_mb"] = total // 1024
        stats["ram_used_mb"]  = used  // 1024
        stats["ram_pct"]      = round(used / total * 100) if total else 0
    except Exception:
        stats["ram_total_mb"] = stats["ram_used_mb"] = stats["ram_pct"] = 0

    # Диск — os.statvfs
    try:
        s = os.statvfs("/")
        total_b = s.f_frsize * s.f_blocks
        free_b  = s.f_frsize * s.f_bavail
        used_b  = total_b - free_b
        stats["disk_total_gb"] = round(total_b / 1024**3, 1)
        stats["disk_used_gb"]  = round(used_b  / 1024**3, 1)
        stats["disk_pct"]      = round(used_b / total_b * 100) if total_b else 0
    except Exception:
        stats["disk_total_gb"] = stats["disk_used_gb"] = stats["disk_pct"] = 0

    return stats


def _uptime_str() -> str:
    secs = int(time.time() - _BOT_START_TIME)
    h, m = divmod(secs // 60, 60)
    d, h = divmod(h, 24)
    parts = []
    if d: parts.append(f"{d}д")
    if h: parts.append(f"{h}ч")
    parts.append(f"{m}м")
    return " ".join(parts)


def _bar(pct: int, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ── Текст панелей ─────────────────────────────────────────────────────────────

def _text_status() -> str:
    maintenance = is_maintenance()
    status_icon = "🔴 Техобслуживание" if maintenance else "🟢 Работает"
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    return (
        f"🤖 <b>Статус бота</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Состояние: {status_icon}\n"
        f"Аптайм: <b>{_uptime_str()}</b>\n"
        f"Время: {now.strftime('%d.%m.%Y %H:%M')} МСК\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


def _text_stats(chat_id: int) -> str:
    try:
        users = get_all_users(chat_id)
        user_count = len(users)
    except Exception:
        user_count = 0

    try:
        gallery = get_gallery(limit=1000, chat_id=chat_id)
        photo_count = len(gallery)
    except Exception:
        photo_count = 0

    today = datetime.date.today().isoformat()
    try:
        swear_total, swear_users = get_daily_swear_report(chat_id, today)
    except Exception:
        swear_total, swear_users = 0, 0

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    return (
        f"📊 <b>Статистика</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Пользователей: <b>{user_count}</b>\n"
        f"🖼 Фото в галерее: <b>{photo_count}</b>\n"
        f"🤬 Матов сегодня: <b>{swear_total}</b> (от {swear_users} чел.)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


def _text_server() -> str:
    s = _get_server_stats()
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    return (
        f"🖥 <b>Сервер</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"CPU нагрузка: {s['load1']:.2f} / {s['load5']:.2f} / {s['load15']:.2f}\n"
        f"       (1м / 5м / 15м)\n\n"
        f"RAM: {s['ram_used_mb']} / {s['ram_total_mb']} МБ  ({s['ram_pct']}%)\n"
        f"{_bar(s['ram_pct'])}\n\n"
        f"Диск: {s['disk_used_gb']} / {s['disk_total_gb']} ГБ  ({s['disk_pct']}%)\n"
        f"{_bar(s['disk_pct'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


# ── Клавиатуры панелей ────────────────────────────────────────────────────────

def _kb_status() -> InlineKeyboardMarkup:
    maintenance = is_maintenance()
    maint_text = "🟢 Выкл. тех.обсл." if maintenance else "🔴 Вкл. тех.обсл."
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Перезапустить бота", callback_data="dash:restart"),
            InlineKeyboardButton(maint_text,              callback_data="dash:toggle_maintenance"),
        ],
        [InlineKeyboardButton("🔄 Обновить", callback_data="dash:refresh_status")],
    ])


def _kb_stats() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Обновить", callback_data="dash:refresh_stats"),
    ]])


def _kb_server() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Обновить", callback_data="dash:refresh_server"),
    ]])


# ── Инициализация дашборда ────────────────────────────────────────────────────

async def setup_dashboard(bot, chat_id: int) -> None:
    """Отправляет 3 сообщения дашборда и закрепляет их. Вызывается когда чат назначается монитором."""
    state = {}
    panels = [
        ("status", _text_status(),     _kb_status()),
        ("stats",  _text_stats(chat_id), _kb_stats()),
        ("server", _text_server(),     _kb_server()),
    ]
    labels = {
        "status": "📌 Панель: Статус бота",
        "stats":  "📌 Панель: Статистика",
        "server": "📌 Панель: Сервер",
    }

    # Удаляем старые сообщения если есть
    old = _load_state()
    if old.get("chat_id") == chat_id:
        for key in ("status", "stats", "server"):
            mid = old.get(key)
            if mid:
                try:
                    await bot.delete_message(chat_id, mid)
                except Exception:
                    pass

    sent_ids = {}
    for key, text, kb in panels:
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=f"<b>{labels[key]}</b>\n\n{text}",
                parse_mode="HTML",
                reply_markup=kb,
            )
            sent_ids[key] = msg.message_id
            try:
                await bot.pin_chat_message(chat_id, msg.message_id, disable_notification=True)
            except Exception as e:
                logger.warning("dashboard: не удалось закрепить %s: %s", key, e)
        except Exception as e:
            logger.error("dashboard: ошибка отправки %s: %s", key, e)

    state = {"chat_id": chat_id, **sent_ids}
    _save_state(state)
    logger.info("dashboard: инициализирован для чата %s, IDs=%s", chat_id, sent_ids)


# ── Обновление панелей ────────────────────────────────────────────────────────

async def _update_panel(bot, chat_id: int, key: str, text: str, kb: InlineKeyboardMarkup) -> None:
    state = _load_state()
    mid = state.get(key)
    if not mid:
        return
    labels = {
        "status": "📌 Панель: Статус бота",
        "stats":  "📌 Панель: Статистика",
        "server": "📌 Панель: Сервер",
    }
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=mid,
            text=f"<b>{labels[key]}</b>\n\n{text}",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            logger.warning("dashboard: edit %s failed: %s", key, e)
    except Exception as e:
        logger.warning("dashboard: edit %s failed: %s", key, e)


async def update_dashboard(bot) -> None:
    """Обновляет все панели дашборда."""
    monitor_id = get_monitor_chat_id()
    if not monitor_id:
        return
    state = _load_state()
    if state.get("chat_id") != monitor_id:
        return
    await _update_panel(bot, monitor_id, "status", _text_status(),          _kb_status())
    await _update_panel(bot, monitor_id, "stats",  _text_stats(monitor_id), _kb_stats())
    await _update_panel(bot, monitor_id, "server", _text_server(),           _kb_server())


# ── Job для периодического обновления ─────────────────────────────────────────

async def dashboard_update_job(context) -> None:
    """PTB job: периодически обновляет дашборд."""
    await update_dashboard(context.bot)


# ── Callback-обработчик кнопок дашборда ──────────────────────────────────────

async def dashboard_callback(update, context) -> None:
    from commands.restart import restart_command
    from config import OWNER_ID

    query = update.callback_query
    if not query:
        return

    if query.from_user.id != OWNER_ID:
        await query.answer("🚫 Только для владельца.", show_alert=True)
        return

    data = query.data
    monitor_id = get_monitor_chat_id()

    if data == "dash:refresh_status":
        await _update_panel(context.bot, monitor_id, "status", _text_status(), _kb_status())
        await query.answer("✅ Обновлено")

    elif data == "dash:refresh_stats":
        await _update_panel(context.bot, monitor_id, "stats", _text_stats(monitor_id), _kb_stats())
        await query.answer("✅ Обновлено")

    elif data == "dash:refresh_server":
        await _update_panel(context.bot, monitor_id, "server", _text_server(), _kb_server())
        await query.answer("✅ Обновлено")

    elif data == "dash:toggle_maintenance":
        new_state = not is_maintenance()
        set_maintenance(new_state)
        state_text = "включён 🔴" if new_state else "выключен 🟢"
        await _update_panel(context.bot, monitor_id, "status", _text_status(), _kb_status())
        await query.answer(f"Режим обслуживания {state_text}", show_alert=False)

    elif data == "dash:restart":
        await query.answer("🔄 Перезапускаю...", show_alert=True)
        # Сохраняем состояние и рестартуем
        import asyncio, sys, os, json as _json
        _RESTART_STATE = "/tmp/tg_restart_state.json"
        try:
            with open(_RESTART_STATE, "w", encoding="utf-8") as f:
                _json.dump({"chat_id": monitor_id, "cmd_mid": None, "note_mid": None}, f)
        except Exception:
            pass
        await asyncio.sleep(0.3)
        os.execl(sys.executable, sys.executable, *sys.argv)

    else:
        await query.answer()
