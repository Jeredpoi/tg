# ==============================================================================
# commands/maintenance.py — /maintenance: режим обслуживания (только владелец)
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes
from config import OWNER_ID
from threading import RLock

_MAINTENANCE = False
_MAINTENANCE_LOCK = RLock()


def is_maintenance() -> bool:
    with _MAINTENANCE_LOCK:
        return _MAINTENANCE


def set_maintenance(value: bool) -> None:
    global _MAINTENANCE
    with _MAINTENANCE_LOCK:
        _MAINTENANCE = value


async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/maintenance on|off — включить/выключить режим обслуживания."""
    if update.effective_user.id != OWNER_ID:
        return

    if update.effective_chat.type != "private":
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        status = "🔴 включён" if is_maintenance() else "🟢 выключен"
        await update.message.reply_text(
            f"🔧 <b>Режим обслуживания</b>\n\n"
            f"Статус: {status}\n\n"
            f"Использование:\n"
            f"/maintenance on — включить\n"
            f"/maintenance off — выключить",
            parse_mode="HTML",
        )
        return

    value = args[0].lower() == "on"
    set_maintenance(value)

    if value:
        await update.message.reply_text(
            "🔴 <b>Режим обслуживания включён</b>\n\n"
            "Все команды пользователей заблокированы.\n"
            "Только владелец может пользоваться ботом.\n\n"
            "<i>Выключить: /maintenance off</i>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "🟢 <b>Режим обслуживания выключен</b>\n\n"
            "Бот работает в обычном режиме.",
            parse_mode="HTML",
        )
