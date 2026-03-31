# ==============================================================================
# commands/dashboard.py — Центр мониторинга и управления (монитор-группа)
# ==============================================================================

import asyncio
import datetime
import json
import logging
import os
import subprocess
import sys
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from chat_config import get_monitor_chat_id, get_main_chat_id
from commands.maintenance import is_maintenance, set_maintenance
from database import (
    get_all_users, get_gallery, get_daily_swear_report, get_and_delete_old_photos,
    get_top_messages, get_top_swears, get_king_today,
)

logger = logging.getLogger(__name__)

_STATE_FILE     = os.path.join(os.path.dirname(__file__), "..", "dashboard_state.json")
_BOT_DIR        = os.path.dirname(os.path.dirname(__file__))
_BOT_START_TIME = time.time()

DASHBOARD_UPDATE_INTERVAL = 300  # 5 минут

# Порядок: control первым (мета-панель), потом по убыванию важности
_PANEL_KEYS = ("control", "status", "actions", "server", "stats", "activity")
_PANEL_LABELS = {
    "control":  "🎛 Управление дашбордом",
    "status":   "📌 Статус бота",
    "actions":  "📌 Быстрые действия",
    "server":   "📌 Сервер",
    "stats":    "📌 Статистика",
    "activity": "📌 Активность",
}


# ── Хранение состояния ────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── Системные метрики ─────────────────────────────────────────────────────────

def _get_server_stats() -> dict:
    stats = {}
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        stats["load1"]  = float(parts[0])
        stats["load5"]  = float(parts[1])
        stats["load15"] = float(parts[2])
        stats["procs"]  = parts[3]
    except Exception:
        stats["load1"] = stats["load5"] = stats["load15"] = 0.0
        stats["procs"] = "?/?"

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

    try:
        pstats = {}
        with open("/proc/self/status") as f:
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    pstats[k.strip()] = v.strip()
        stats["bot_rss_mb"] = int(pstats.get("VmRSS", "0 kB").split()[0]) // 1024
    except Exception:
        stats["bot_rss_mb"] = 0

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


def _get_git_info() -> tuple[str, str]:
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=_BOT_DIR, stderr=subprocess.DEVNULL, text=True, timeout=3
        ).strip()
        commit = subprocess.check_output(
            ["git", "log", "-1", "--format=%h %s"],
            cwd=_BOT_DIR, stderr=subprocess.DEVNULL, text=True, timeout=3
        ).strip()
        return branch, commit
    except Exception:
        return "?", "?"


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


def _now_msk() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))


# ── Текст панелей ─────────────────────────────────────────────────────────────

def _text_status() -> str:
    maintenance = is_maintenance()
    status_icon = "🔴 Техобслуживание" if maintenance else "🟢 Работает"
    branch, commit = _get_git_info()
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    now = _now_msk()
    return (
        f"Состояние: {status_icon}\n"
        f"Аптайм: <b>{_uptime_str()}</b>\n"
        f"Python: {py_ver}\n"
        f"Ветка: <code>{branch}</code>\n"
        f"Коммит: <code>{commit[:55]}</code>\n"
        f"Время: {now.strftime('%d.%m.%Y %H:%M')} МСК\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


async def _text_stats_async(bot=None) -> str:
    """Статистика из основной группы. bot передаётся для получения реального числа участников."""
    main_id = get_main_chat_id()
    chat_label = "основная группа" if main_id else "⚠️ нет основной группы"

    real_members = None
    db_users     = 0
    photo_count  = 0
    swear_total  = 0
    swear_top: list = []

    if main_id:
        # Реальное число участников через Telegram API
        if bot:
            try:
                real_members = await bot.get_chat_member_count(main_id)
            except Exception:
                pass
        # Пользователи в БД (взаимодействовавшие с ботом)
        try:
            db_users = len(get_all_users(main_id))
        except Exception:
            pass
        try:
            photo_count = len(get_gallery(limit=9999, chat_id=main_id))
        except Exception:
            pass
        today = datetime.date.today().isoformat()
        try:
            swear_total, swear_top = get_daily_swear_report(main_id, today)
        except Exception:
            pass

    members_line = (
        f"👥 Участников: <b>{real_members}</b> (в боте: {db_users})\n"
        if real_members is not None
        else f"👥 В базе: <b>{db_users}</b>\n"
    )

    top_lines = ""
    if swear_top:
        top_lines = "\n"
        for i, (name, cnt) in enumerate(swear_top[:3], 1):
            top_lines += f"  {i}. {name}: {cnt}\n"

    now = _now_msk()
    return (
        f"Источник: <i>{chat_label}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{members_line}"
        f"🖼 Фото в галерее: <b>{photo_count}</b>\n"
        f"🤬 Матов сегодня: <b>{swear_total}</b>{top_lines}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


def _text_server() -> str:
    s = _get_server_stats()
    now = _now_msk()
    return (
        f"CPU (1/5/15м): {s['load1']:.2f} / {s['load5']:.2f} / {s['load15']:.2f}\n"
        f"Процессов: {s['procs']}\n\n"
        f"RAM: {s['ram_used_mb']} / {s['ram_total_mb']} МБ  ({s['ram_pct']}%)\n"
        f"{_bar(s['ram_pct'])}\n"
        f"Бот занимает: {s['bot_rss_mb']} МБ\n\n"
        f"Диск: {s['disk_used_gb']} / {s['disk_total_gb']} ГБ  ({s['disk_pct']}%)\n"
        f"{_bar(s['disk_pct'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


def _text_actions() -> str:
    now = _now_msk()
    return (
        f"Кнопки быстрых действий:\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


async def _text_activity_async() -> str:
    """Топ активных пользователей и король дня из основной группы."""
    main_id = get_main_chat_id()
    now = _now_msk()
    if not main_id:
        return (
            f"⚠️ Основная группа не назначена\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
        )

    top_msg, top_sw, king = [], [], None
    try:
        top_msg = get_top_messages(chat_id=main_id, limit=5)
    except Exception:
        pass
    try:
        top_sw = get_top_swears(chat_id=main_id, limit=3)
    except Exception:
        pass
    try:
        king = get_king_today(main_id)
    except Exception:
        pass

    def _fmt_top(rows, name_key="first_name", count_key="msg_count") -> str:
        lines = []
        for i, r in enumerate(rows, 1):
            rd = dict(r)
            name  = rd.get(name_key) or rd.get("username") or "?"
            count = rd.get(count_key, 0)
            lines.append(f"  {i}. {name} — {count}")
        return "\n".join(lines) if lines else "  нет данных"

    king_line = ""
    if king:
        k = dict(king)
        king_name = k.get("first_name") or k.get("username") or "?"
        king_line = f"👑 Король дня: <b>{king_name}</b>\n"

    return (
        f"{king_line}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 Топ по сообщениям:\n{_fmt_top(top_msg, count_key='msg_count')}\n\n"
        f"🤬 Топ по матам (всего):\n{_fmt_top(top_sw, count_key='swear_count')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


def _text_control() -> str:
    """Мета-панель: статус каждой панели и управление дашбордом."""
    state = _load_state()
    now = _now_msk()
    lines = []
    for key in _PANEL_KEYS:
        if key == "control":
            continue
        mid = state.get(key)
        icon = "✅" if mid else "❌"
        lines.append(f"{icon} {_PANEL_LABELS[key]}")
    panels_status = "\n".join(lines)
    return (
        f"Статус панелей:\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{panels_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


# ── Клавиатуры ────────────────────────────────────────────────────────────────

def _kb_status() -> InlineKeyboardMarkup:
    maintenance = is_maintenance()
    maint_text = "🟢 Выкл. тех.обсл." if maintenance else "🔴 Вкл. тех.обсл."
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Перезапустить",      callback_data="dash:restart"),
            InlineKeyboardButton(maint_text,               callback_data="dash:toggle_maintenance"),
        ],
        [InlineKeyboardButton("📥 Git Pull + Restart",    callback_data="dash:git_pull_restart")],
        [InlineKeyboardButton("🔄 Обновить",              callback_data="dash:refresh_status")],
    ])


def _kb_stats() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Обновить", callback_data="dash:refresh_stats"),
    ]])


def _kb_server() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Обновить", callback_data="dash:refresh_server"),
    ]])


def _kb_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑 Кэш аватаров",       callback_data="dash:clear_avatars"),
            InlineKeyboardButton("🧹 Фото >30 дней",      callback_data="dash:cleanup_photos"),
        ],
        [InlineKeyboardButton("🔄 Обновить все панели",   callback_data="dash:refresh_all")],
    ])


def _kb_activity() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Обновить", callback_data="dash:refresh_activity"),
    ]])


def _kb_control() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Восстановить недостающие", callback_data="dash:restore_missing")],
        [InlineKeyboardButton("🔄 Пересоздать все панели",   callback_data="dash:recreate_all")],
        [InlineKeyboardButton("📌 Перезакрепить все",        callback_data="dash:repin_all")],
        [InlineKeyboardButton("🗑 Удалить все панели",       callback_data="dash:delete_all")],
        [InlineKeyboardButton("🔄 Обновить эту панель",      callback_data="dash:refresh_control")],
    ])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_all_panel_texts(bot) -> dict:
    """Возвращает dict key→(text, kb) для всех панелей."""
    stats_text    = await _text_stats_async(bot)
    activity_text = await _text_activity_async()
    return {
        "control":  (_text_control(),   _kb_control()),
        "status":   (_text_status(),    _kb_status()),
        "actions":  (_text_actions(),   _kb_actions()),
        "server":   (_text_server(),    _kb_server()),
        "stats":    (stats_text,        _kb_stats()),
        "activity": (activity_text,     _kb_activity()),
    }


# ── Инициализация дашборда ────────────────────────────────────────────────────

async def setup_dashboard(bot, chat_id: int) -> None:
    """Отправляет все панели дашборда и закрепляет их."""
    panel_data = await _get_all_panel_texts(bot)
    panels = [(key, *panel_data[key]) for key in _PANEL_KEYS]

    # Удаляем старые сообщения если есть
    old = _load_state()
    if old.get("chat_id") == chat_id:
        for key in _PANEL_KEYS:
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
                text=f"<b>{_PANEL_LABELS[key]}</b>\n\n{text}",
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

    if not sent_ids:
        logger.error("dashboard: ни одна панель не отправлена, состояние не сохранено")
        return
    if len(sent_ids) < len(_PANEL_KEYS):
        logger.warning("dashboard: %d из %d панелей отправлено", len(sent_ids), len(_PANEL_KEYS))
    _save_state({"chat_id": chat_id, **sent_ids})
    logger.info("dashboard: инициализирован для чата %s, IDs=%s", chat_id, sent_ids)


# ── Обновление одной панели ───────────────────────────────────────────────────

async def _update_panel(bot, chat_id: int, key: str, text: str, kb: InlineKeyboardMarkup) -> None:
    state = _load_state()
    mid = state.get(key)
    if not mid:
        return
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=mid,
            text=f"<b>{_PANEL_LABELS[key]}</b>\n\n{text}",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except BadRequest as e:
        err = str(e).lower()
        if "not modified" in err:
            pass
        elif "message to edit not found" in err or "message_id_invalid" in err:
            state.pop(key, None)
            _save_state(state)
            logger.warning("dashboard: панель %s удалена, ID сброшен", key)
        else:
            logger.warning("dashboard: edit %s failed: %s", key, e)
    except Exception as e:
        logger.warning("dashboard: edit %s failed: %s", key, e)


async def update_dashboard(bot) -> None:
    """Обновляет все существующие панели."""
    monitor_id = get_monitor_chat_id()
    if not monitor_id:
        return
    state = _load_state()
    if state.get("chat_id") != monitor_id:
        return
    panel_data = await _get_all_panel_texts(bot)
    for key in _PANEL_KEYS:
        text, kb = panel_data[key]
        await _update_panel(bot, monitor_id, key, text, kb)


# ── Job ───────────────────────────────────────────────────────────────────────

async def dashboard_update_job(context) -> None:
    await update_dashboard(context.bot)


# ── Git pull + restart ────────────────────────────────────────────────────────

async def _git_pull_and_restart(bot, monitor_id: int) -> None:
    status_msg = None
    try:
        status_msg = await bot.send_message(monitor_id, "⏳ <b>Git Pull...</b>", parse_mode="HTML")
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=_BOT_DIR, capture_output=True, text=True, timeout=30,
        )
        pull_out = (result.stdout + result.stderr).strip()[:400]
        success  = result.returncode == 0
    except subprocess.TimeoutExpired:
        pull_out, success = "Timeout (>30s)", False
    except Exception as e:
        pull_out, success = str(e), False

    if not success:
        try:
            if status_msg:
                await bot.edit_message_text(
                    chat_id=monitor_id, message_id=status_msg.message_id,
                    text=f"❌ <b>Git pull не удался:</b>\n<pre>{pull_out}</pre>",
                    parse_mode="HTML",
                )
        except Exception:
            pass
        return

    try:
        if status_msg:
            await bot.edit_message_text(
                chat_id=monitor_id, message_id=status_msg.message_id,
                text=f"✅ <b>Git pull выполнен:</b>\n<pre>{pull_out}</pre>\n\n🔄 Перезапускаю...",
                parse_mode="HTML",
            )
    except Exception:
        pass

    await asyncio.sleep(0.5)
    try:
        subprocess.Popen(
            ["systemctl", "restart", "tg-webserver"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    try:
        with open("/tmp/tg_restart_state.json", "w", encoding="utf-8") as f:
            json.dump({"chat_id": monitor_id}, f)
    except Exception:
        pass

    os.execl(sys.executable, sys.executable, *sys.argv)


# ── Callback ──────────────────────────────────────────────────────────────────

async def dashboard_callback(update, context) -> None:
    from config import OWNER_ID

    query = update.callback_query
    if not query:
        return

    if query.from_user.id != OWNER_ID:
        await query.answer("🚫 Только для владельца.", show_alert=True)
        return

    data       = query.data
    monitor_id = get_monitor_chat_id()
    if not monitor_id:
        await query.answer("🚫 Дашборд не настроен — выбери монитор-группу в /settings.", show_alert=True)
        return

    # ── Обновление отдельных панелей ──
    if data == "dash:refresh_status":
        await query.answer("🔄 Обновляю...")
        await _update_panel(context.bot, monitor_id, "status", _text_status(), _kb_status())

    elif data == "dash:refresh_stats":
        await query.answer("🔄 Обновляю...")
        text = await _text_stats_async(context.bot)
        await _update_panel(context.bot, monitor_id, "stats", text, _kb_stats())

    elif data == "dash:refresh_server":
        await query.answer("🔄 Обновляю...")
        await _update_panel(context.bot, monitor_id, "server", _text_server(), _kb_server())

    elif data == "dash:refresh_control":
        await query.answer("🔄 Обновляю...")
        await _update_panel(context.bot, monitor_id, "control", _text_control(), _kb_control())

    elif data == "dash:refresh_activity":
        await query.answer("🔄 Обновляю...")
        text = await _text_activity_async()
        await _update_panel(context.bot, monitor_id, "activity", text, _kb_activity())

    elif data == "dash:refresh_all":
        await query.answer("🔄 Обновляю все панели...")
        await update_dashboard(context.bot)

    # ── Управление ботом ──
    elif data == "dash:toggle_maintenance":
        new_state = not is_maintenance()
        set_maintenance(new_state)
        state_text = "включён 🔴" if new_state else "выключен 🟢"
        await _update_panel(context.bot, monitor_id, "status", _text_status(), _kb_status())
        await query.answer(f"Режим обслуживания {state_text}")

    elif data == "dash:restart":
        await query.answer("🔄 Перезапускаю...", show_alert=True)
        try:
            with open("/tmp/tg_restart_state.json", "w", encoding="utf-8") as f:
                json.dump({"chat_id": monitor_id}, f)
        except Exception:
            pass
        await asyncio.sleep(0.3)
        os.execl(sys.executable, sys.executable, *sys.argv)

    elif data == "dash:git_pull_restart":
        await query.answer("📥 Запускаю git pull...", show_alert=True)
        asyncio.create_task(_git_pull_and_restart(context.bot, monitor_id))

    # ── Быстрые действия ──
    elif data == "dash:clear_avatars":
        try:
            bot_module = sys.modules.get("bot")
            cache  = getattr(bot_module, "_avatar_cache_set", None) if bot_module else None
            count  = len(cache) if cache is not None else 0
            if cache is not None:
                cache.clear()
            await query.answer(f"🗑 Кэш аватаров очищен ({count} записей)")
        except Exception as e:
            await query.answer(f"❌ Ошибка: {e}", show_alert=True)
        await _update_panel(context.bot, monitor_id, "actions", _text_actions(), _kb_actions())

    elif data == "dash:cleanup_photos":
        await query.answer("🧹 Удаляю...")
        try:
            deleted    = get_and_delete_old_photos(30)
            count      = len(deleted) if deleted else 0
            photos_dir = os.path.join(_BOT_DIR, "photos")
            for key, media_type in deleted:
                ext = ".mp4" if media_type == "video" else ".jpg"
                try:
                    os.remove(os.path.join(photos_dir, key + ext))
                except FileNotFoundError:
                    pass
            await query.answer(f"🧹 Удалено {count} старых фото", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Ошибка: {e}", show_alert=True)
        text = await _text_stats_async(context.bot)
        await _update_panel(context.bot, monitor_id, "stats", text, _kb_stats())

    # ── Управление дашбордом (мета-панель) ──
    elif data == "dash:restore_missing":
        """Отправляет только те панели, которых нет в состоянии."""
        await query.answer("➕ Восстанавливаю недостающие панели...")
        state      = _load_state()
        panel_data = await _get_all_panel_texts(context.bot)
        restored   = 0
        for key in _PANEL_KEYS:
            if state.get(key):
                continue  # уже есть
            text, kb = panel_data[key]
            try:
                msg = await context.bot.send_message(
                    chat_id=monitor_id,
                    text=f"<b>{_PANEL_LABELS[key]}</b>\n\n{text}",
                    parse_mode="HTML",
                    reply_markup=kb,
                )
                state[key] = msg.message_id
                restored += 1
                try:
                    await context.bot.pin_chat_message(monitor_id, msg.message_id, disable_notification=True)
                except Exception:
                    pass
            except Exception as e:
                logger.error("dashboard restore_missing %s: %s", key, e)
        state["chat_id"] = monitor_id
        _save_state(state)
        await _update_panel(context.bot, monitor_id, "control", _text_control(), _kb_control())
        if restored == 0:
            await query.answer("✅ Все панели на месте", show_alert=True)
        else:
            await query.answer(f"✅ Восстановлено {restored} панел(ей)", show_alert=True)

    elif data == "dash:recreate_all":
        await query.answer("🔄 Пересоздаю все панели...")
        await setup_dashboard(context.bot, monitor_id)

    elif data == "dash:repin_all":
        await query.answer("📌 Перезакрепляю...")
        state   = _load_state()
        pinned  = 0
        failed  = 0
        for key in _PANEL_KEYS:
            mid = state.get(key)
            if not mid:
                continue
            try:
                await context.bot.pin_chat_message(monitor_id, mid, disable_notification=True)
                pinned += 1
            except Exception as e:
                logger.warning("repin %s: %s", key, e)
                failed += 1
        result = f"📌 Закреплено: {pinned}"
        if failed:
            result += f", не удалось: {failed}"
        await query.answer(result, show_alert=True)

    elif data == "dash:delete_all":
        await query.answer("🗑 Удаляю все панели...")
        state = _load_state()
        for key in _PANEL_KEYS:
            mid = state.get(key)
            if mid:
                try:
                    await context.bot.delete_message(monitor_id, mid)
                except Exception:
                    pass
        _save_state({})
        await query.answer("🗑 Все панели удалены. Пересоздай через /settings.", show_alert=True)

    else:
        await query.answer()


# ── Команда /dashboard ────────────────────────────────────────────────────────

async def dashboard_command(update, context) -> None:
    """/dashboard — отправить/пересоздать панели мониторинга (только владелец)."""
    from config import OWNER_ID
    user = update.effective_user
    if not user or user.id != OWNER_ID:
        return

    # Удаляем команду немедленно
    try:
        await update.message.delete()
    except Exception:
        pass

    # Определяем целевой чат — только монитор-группа, fallback запрещён
    monitor_id = get_monitor_chat_id()
    if not monitor_id:
        try:
            await context.bot.send_message(
                user.id,
                "❌ Монитор-группа не назначена.\n"
                "Сначала назначь её: /settings → Чаты бота → нужная группа → 🖥 Сделать монитором",
            )
        except Exception:
            pass
        return

    # Уведомляем что начали (в ЛС владельцу, чтобы не мусорить в группе)
    progress = None
    try:
        progress = await context.bot.send_message(
            user.id,
            f"⏳ Отправляю панели дашборда в чат <code>{monitor_id}</code>...",
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        await setup_dashboard(context.bot, monitor_id)
        if progress:
            await progress.edit_text("✅ Дашборд отправлен и закреплён!")
            await asyncio.sleep(5)
            await progress.delete()
    except Exception as e:
        logger.error("dashboard_command error: %s", e, exc_info=True)
        if progress:
            await progress.edit_text(f"❌ Ошибка: {e}")
