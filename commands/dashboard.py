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
from database import get_all_users, get_gallery, get_daily_swear_report, get_and_delete_old_photos  # noqa: F401

logger = logging.getLogger(__name__)

_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "dashboard_state.json")
_BOT_DIR    = os.path.dirname(os.path.dirname(__file__))
_BOT_START_TIME = time.time()

# Интервал авто-обновления (секунды)
DASHBOARD_UPDATE_INTERVAL = 300  # 5 минут

# Все ключи панелей в порядке отправки
_PANEL_KEYS = ("status", "stats", "server", "actions")
_PANEL_LABELS = {
    "status":  "📌 Панель: Статус бота",
    "stats":   "📌 Панель: Статистика",
    "server":  "📌 Панель: Сервер",
    "actions": "📌 Панель: Быстрые действия",
}


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


# ── Системные метрики ─────────────────────────────────────────────────────────

def _get_server_stats() -> dict:
    stats = {}
    # CPU — /proc/loadavg
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        stats["load1"]  = float(parts[0])
        stats["load5"]  = float(parts[1])
        stats["load15"] = float(parts[2])
        stats["procs"]  = parts[3]   # running/total
    except Exception:
        stats["load1"] = stats["load5"] = stats["load15"] = 0.0
        stats["procs"] = "?/?"

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

    # Процесс бота — /proc/self/status
    try:
        pstats = {}
        with open("/proc/self/status") as f:
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    pstats[k.strip()] = v.strip()
        vm_rss = pstats.get("VmRSS", "0 kB").split()[0]
        stats["bot_rss_mb"] = int(vm_rss) // 1024
    except Exception:
        stats["bot_rss_mb"] = 0

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


def _get_git_info() -> tuple[str, str]:
    """Возвращает (branch, short_commit)."""
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


# ── Текст панелей ─────────────────────────────────────────────────────────────

def _text_status() -> str:
    maintenance = is_maintenance()
    status_icon = "🔴 Техобслуживание" if maintenance else "🟢 Работает"
    branch, commit = _get_git_info()
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    return (
        f"Состояние: {status_icon}\n"
        f"Аптайм: <b>{_uptime_str()}</b>\n"
        f"Python: {py_ver}\n"
        f"Ветка: <code>{branch}</code>\n"
        f"Коммит: <code>{commit[:50]}</code>\n"
        f"Время: {now.strftime('%d.%m.%Y %H:%M')} МСК\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


def _text_stats() -> str:
    """Статистика из основной группы."""
    main_id = get_main_chat_id()
    chat_label = f"основная группа" if main_id else "нет основной группы"

    user_count = 0
    photo_count = 0
    swear_total = 0
    swear_top: list = []

    if main_id:
        try:
            user_count = len(get_all_users(main_id))
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

    top_lines = ""
    if swear_top:
        top_lines = "\n"
        for i, (name, cnt) in enumerate(swear_top[:3], 1):
            top_lines += f"  {i}. {name}: {cnt}\n"

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    return (
        f"Источник: <i>{chat_label}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Пользователей: <b>{user_count}</b>\n"
        f"🖼 Фото в галерее: <b>{photo_count}</b>\n"
        f"🤬 Матов сегодня: <b>{swear_total}</b>{top_lines}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


def _text_server() -> str:
    s = _get_server_stats()
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
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
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    return (
        f"Нажми кнопку для быстрого действия.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Обновлено: {now.strftime('%H:%M:%S')}</i>"
    )


# ── Клавиатуры панелей ────────────────────────────────────────────────────────

def _kb_status() -> InlineKeyboardMarkup:
    maintenance = is_maintenance()
    maint_text = "🟢 Выкл. тех.обсл." if maintenance else "🔴 Вкл. тех.обсл."
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Перезапустить",    callback_data="dash:restart"),
            InlineKeyboardButton(maint_text,             callback_data="dash:toggle_maintenance"),
        ],
        [
            InlineKeyboardButton("📥 Git Pull + Restart", callback_data="dash:git_pull_restart"),
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


def _kb_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑 Очистить кэш аватаров",  callback_data="dash:clear_avatars"),
            InlineKeyboardButton("🧹 Удалить фото >30 дней",  callback_data="dash:cleanup_photos"),
        ],
        [
            InlineKeyboardButton("🔄 Обновить все панели",    callback_data="dash:refresh_all"),
        ],
    ])


# ── Инициализация дашборда ────────────────────────────────────────────────────

async def setup_dashboard(bot, chat_id: int) -> None:
    """Отправляет панели дашборда и закрепляет их."""
    panels = [
        ("status",  _text_status(),   _kb_status()),
        ("stats",   _text_stats(),    _kb_stats()),
        ("server",  _text_server(),   _kb_server()),
        ("actions", _text_actions(),  _kb_actions()),
    ]

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

    _save_state({"chat_id": chat_id, **sent_ids})
    logger.info("dashboard: инициализирован для чата %s, IDs=%s", chat_id, sent_ids)


# ── Обновление панели ─────────────────────────────────────────────────────────

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
            pass  # ничего не изменилось — ок
        elif "message to edit not found" in err or "message_id_invalid" in err:
            # Сообщение удалено — сбрасываем ID чтобы не пытаться снова
            state.pop(key, None)
            _save_state(state)
            logger.warning("dashboard: панель %s удалена, ID сброшен", key)
        else:
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
    await _update_panel(bot, monitor_id, "status",  _text_status(),   _kb_status())
    await _update_panel(bot, monitor_id, "stats",   _text_stats(),    _kb_stats())
    await _update_panel(bot, monitor_id, "server",  _text_server(),   _kb_server())
    await _update_panel(bot, monitor_id, "actions", _text_actions(),  _kb_actions())


# ── Job для периодического обновления ─────────────────────────────────────────

async def dashboard_update_job(context) -> None:
    await update_dashboard(context.bot)


# ── Git pull + restart ────────────────────────────────────────────────────────

async def _git_pull_and_restart(bot, monitor_id: int) -> None:
    """Запускает git pull, уведомляет о результате, перезапускает бота и вебсервер."""
    import json as _json

    # Сообщение о начале
    status_msg = None
    try:
        status_msg = await bot.send_message(
            monitor_id,
            "⏳ <b>Git Pull...</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # git pull
    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=_BOT_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        pull_out = (result.stdout + result.stderr).strip()[:300]
        success = result.returncode == 0
    except subprocess.TimeoutExpired:
        pull_out = "Timeout (>30s)"
        success = False
    except Exception as e:
        pull_out = str(e)
        success = False

    if not success:
        try:
            if status_msg:
                await bot.edit_message_text(
                    chat_id=monitor_id,
                    message_id=status_msg.message_id,
                    text=f"❌ <b>Git pull не удался:</b>\n<pre>{pull_out}</pre>",
                    parse_mode="HTML",
                )
        except Exception:
            pass
        return

    try:
        if status_msg:
            await bot.edit_message_text(
                chat_id=monitor_id,
                message_id=status_msg.message_id,
                text=f"✅ <b>Git pull выполнен:</b>\n<pre>{pull_out}</pre>\n\n🔄 Перезапускаю...",
                parse_mode="HTML",
            )
    except Exception:
        pass

    await asyncio.sleep(0.5)

    # Перезапускаем вебсервер отдельно если systemctl доступен
    try:
        subprocess.Popen(
            ["systemctl", "restart", "tg-webserver"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # systemctl недоступен в dev-окружении

    # Сохраняем состояние для уведомления после перезапуска
    try:
        with open("/tmp/tg_restart_state.json", "w", encoding="utf-8") as f:
            _json.dump({"chat_id": monitor_id, "cmd_mid": None, "note_mid": None}, f)
    except Exception:
        pass

    # Перезапускаем бота
    os.execl(sys.executable, sys.executable, *sys.argv)


# ── Callback-обработчик кнопок дашборда ──────────────────────────────────────

async def dashboard_callback(update, context) -> None:
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
        await query.answer("🔄 Обновляю...")
        await _update_panel(context.bot, monitor_id, "status", _text_status(), _kb_status())

    elif data == "dash:refresh_stats":
        await query.answer("🔄 Обновляю...")
        await _update_panel(context.bot, monitor_id, "stats", _text_stats(), _kb_stats())

    elif data == "dash:refresh_server":
        await query.answer("🔄 Обновляю...")
        await _update_panel(context.bot, monitor_id, "server", _text_server(), _kb_server())

    elif data == "dash:refresh_all":
        await query.answer("🔄 Обновляю все панели...")
        await update_dashboard(context.bot)

    elif data == "dash:toggle_maintenance":
        new_state = not is_maintenance()
        set_maintenance(new_state)
        state_text = "включён 🔴" if new_state else "выключен 🟢"
        await _update_panel(context.bot, monitor_id, "status", _text_status(), _kb_status())
        await query.answer(f"Режим обслуживания {state_text}")

    elif data == "dash:restart":
        await query.answer("🔄 Перезапускаю...", show_alert=True)
        import json as _json
        try:
            with open("/tmp/tg_restart_state.json", "w", encoding="utf-8") as f:
                _json.dump({"chat_id": monitor_id, "cmd_mid": None, "note_mid": None}, f)
        except Exception:
            pass
        await asyncio.sleep(0.3)
        os.execl(sys.executable, sys.executable, *sys.argv)

    elif data == "dash:git_pull_restart":
        await query.answer("📥 Запускаю git pull...", show_alert=True)
        # Запускаем в фоне чтобы ответить на callback до execl
        asyncio.create_task(_git_pull_and_restart(context.bot, monitor_id))

    elif data == "dash:clear_avatars":
        # Очищаем кэш аватаров через модуль bot (избегаем циклического импорта — импортируем здесь)
        try:
            import importlib
            bot_module = sys.modules.get("bot") or importlib.import_module("bot")
            cache = getattr(bot_module, "_avatar_cache_set", None)
            count = len(cache) if cache is not None else 0
            if cache is not None:
                cache.clear()
            await query.answer(f"🗑 Кэш аватаров очищен ({count} записей)")
        except Exception as e:
            await query.answer(f"❌ Ошибка: {e}", show_alert=True)
        await _update_panel(context.bot, monitor_id, "actions", _text_actions(), _kb_actions())

    elif data == "dash:cleanup_photos":
        await query.answer("🧹 Удаляю старые фото...")
        try:
            deleted = get_and_delete_old_photos(30)
            count = len(deleted) if deleted else 0
            # Удаляем файлы с диска; deleted — список (key, media_type)
            photos_dir = os.path.join(_BOT_DIR, "photos")
            for key, media_type in deleted:
                ext = ".mp4" if media_type == "video" else ".jpg"
                fpath = os.path.join(photos_dir, key + ext)
                try:
                    os.remove(fpath)
                except FileNotFoundError:
                    pass
            await query.answer(f"🧹 Удалено {count} старых фото", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Ошибка: {e}", show_alert=True)
        await _update_panel(context.bot, monitor_id, "stats", _text_stats(), _kb_stats())

    else:
        await query.answer()
