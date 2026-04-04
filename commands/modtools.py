# ==============================================================================
# commands/modtools.py — Инструменты модерации и управления для владельца
# /ban, /kick, /mute, /unmute, /pin, /unpin, /synccmds, /giveach, /announce
# ==============================================================================

import datetime
import logging
import re

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from config import OWNER_ID
from chat_config import sync_bot_commands, get_main_chat_id

logger = logging.getLogger(__name__)

_MSK = datetime.timezone(datetime.timedelta(hours=3))

# ── Вспомогательные ───────────────────────────────────────────────────────────

def _parse_duration(arg: str) -> int | None:
    """
    Парсит строку длительности.
    Форматы: 10, 10m, 2h, 1d → секунды.
    По умолчанию единица — минуты.
    Возвращает None при ошибке.
    """
    arg = arg.strip().lower()
    m = re.fullmatch(r"(\d+)([mhd]?)", arg)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2) or "m"
    if unit == "m":
        return val * 60
    if unit == "h":
        return val * 3600
    if unit == "d":
        return val * 86400
    return None


def _owner_only(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == OWNER_ID


async def _quick_reply(update: Update, text: str, autodel: int = 15) -> None:
    """Отправляет сообщение, удаляет команду, авто-удаляет ответ через autodel сек."""
    msg = await update.effective_message.reply_text(text, parse_mode="HTML")
    try:
        await update.effective_message.delete()
    except Exception:
        pass

    async def _del():
        import asyncio
        await asyncio.sleep(autodel)
        try:
            await msg.delete()
        except Exception:
            pass

    import asyncio
    asyncio.create_task(_del())


# ── /ban — забанить пользователя ──────────────────────────────────────────────

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ban — забанить участника (в ответ на его сообщение). Только владелец."""
    if not _owner_only(update):
        return

    msg = update.effective_message
    if not msg.reply_to_message:
        await _quick_reply(update, "❌ Ответь на сообщение пользователя, которого хочешь забанить.")
        return

    target = msg.reply_to_message.from_user
    if target.is_bot:
        await _quick_reply(update, "❌ Нельзя банить ботов.")
        return
    if target.id == OWNER_ID:
        await _quick_reply(update, "❌ Нельзя банить владельца.")
        return

    reason = " ".join(context.args) if context.args else "нарушение правил"

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        name = target.first_name or target.username or str(target.id)
        await _quick_reply(update,
            f"🔨 <b>{name}</b> забанен.\n<i>Причина: {reason}</i>",
            autodel=20,
        )
    except Exception as e:
        await _quick_reply(update, f"❌ Ошибка: {e}")


# ── /kick — выгнать без бана ──────────────────────────────────────────────────

async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/kick — выгнать участника (может вернуться). Только владелец."""
    if not _owner_only(update):
        return

    msg = update.effective_message
    if not msg.reply_to_message:
        await _quick_reply(update, "❌ Ответь на сообщение пользователя, которого хочешь выгнать.")
        return

    target = msg.reply_to_message.from_user
    if target.is_bot:
        await _quick_reply(update, "❌ Нельзя кикать ботов.")
        return
    if target.id == OWNER_ID:
        await _quick_reply(update, "❌ Нельзя кикать владельца.")
        return

    try:
        chat_id = update.effective_chat.id
        await context.bot.ban_chat_member(chat_id, target.id)
        await context.bot.unban_chat_member(chat_id, target.id)
        name = target.first_name or target.username or str(target.id)
        await _quick_reply(update, f"👢 <b>{name}</b> выгнан из чата.", autodel=20)
    except Exception as e:
        await _quick_reply(update, f"❌ Ошибка: {e}")


# ── /mute — ограничить участника ─────────────────────────────────────────────

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/mute [время] — ограничить участника (10m, 2h, 1d). Только владелец."""
    if not _owner_only(update):
        return

    msg = update.effective_message
    if not msg.reply_to_message:
        await _quick_reply(update, "❌ Ответь на сообщение пользователя, которого хочешь замутить.")
        return

    target = msg.reply_to_message.from_user
    if target.is_bot:
        await _quick_reply(update, "❌ Нельзя мутить ботов.")
        return
    if target.id == OWNER_ID:
        await _quick_reply(update, "❌ Нельзя мутить владельца.")
        return

    duration_str = context.args[0] if context.args else "10m"
    secs = _parse_duration(duration_str)
    if secs is None:
        await _quick_reply(update, "❌ Неверный формат времени. Примеры: <code>10m</code>, <code>2h</code>, <code>1d</code>")
        return

    until = datetime.datetime.now(_MSK) + datetime.timedelta(seconds=secs)

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            target.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
            until_date=until,
        )
        name = target.first_name or target.username or str(target.id)
        human = _human_duration(secs)
        await _quick_reply(update, f"🔇 <b>{name}</b> замучен на {human}.", autodel=20)
    except Exception as e:
        await _quick_reply(update, f"❌ Ошибка: {e}")


def _human_duration(secs: int) -> str:
    if secs < 60:
        return f"{secs} сек."
    if secs < 3600:
        return f"{secs // 60} мин."
    if secs < 86400:
        return f"{secs // 3600} ч."
    return f"{secs // 86400} дн."


# ── /unmute — снять ограничения ───────────────────────────────────────────────

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/unmute — снять мут с участника. Только владелец."""
    if not _owner_only(update):
        return

    msg = update.effective_message
    if not msg.reply_to_message:
        await _quick_reply(update, "❌ Ответь на сообщение пользователя, которого хочешь размутить.")
        return

    target = msg.reply_to_message.from_user

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_send_polls=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            ),
        )
        name = target.first_name or target.username or str(target.id)
        await _quick_reply(update, f"🔊 <b>{name}</b> размучен.", autodel=15)
    except Exception as e:
        await _quick_reply(update, f"❌ Ошибка: {e}")


# ── /pin — закрепить сообщение ────────────────────────────────────────────────

async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pin — закрепить сообщение (в ответ). Только владелец."""
    if not _owner_only(update):
        return

    msg = update.effective_message
    if not msg.reply_to_message:
        await _quick_reply(update, "❌ Ответь на сообщение, которое хочешь закрепить.")
        return

    try:
        await context.bot.pin_chat_message(
            update.effective_chat.id,
            msg.reply_to_message.message_id,
            disable_notification=False,
        )
        try:
            await msg.delete()
        except Exception:
            pass
    except Exception as e:
        await _quick_reply(update, f"❌ Ошибка: {e}")


# ── /unpin — открепить последнее закреплённое ────────────────────────────────

async def unpin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/unpin — открепить закреплённое сообщение. Только владелец."""
    if not _owner_only(update):
        return

    try:
        await context.bot.unpin_chat_message(update.effective_chat.id)
        try:
            await update.effective_message.delete()
        except Exception:
            pass
    except Exception as e:
        await _quick_reply(update, f"❌ Ошибка: {e}")


# ── /synccmds — принудительная синхронизация команд с Bot Father ─────────────

async def synccmds_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/synccmds — принудительно обновить список команд в Bot Father. Только владелец, только личка."""
    if not _owner_only(update):
        return

    try:
        await update.effective_message.delete()
    except Exception:
        pass

    try:
        await sync_bot_commands(context.bot)
        msg = await context.bot.send_message(
            update.effective_chat.id,
            "✅ Команды синхронизированы с Bot Father!\n\n"
            "<i>Список команд в Telegram обновлён.</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        msg = await context.bot.send_message(
            update.effective_chat.id,
            f"❌ Ошибка синхронизации: {e}",
        )

    import asyncio
    async def _del():
        await asyncio.sleep(20)
        try:
            await msg.delete()
        except Exception:
            pass
    asyncio.create_task(_del())


# ── /giveach — вручную выдать ачивку пользователю ────────────────────────────

async def giveach_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/giveach <user_id> <ach_id> — вручную выдать ачивку. Только владелец, только личка."""
    if not _owner_only(update):
        return

    try:
        await update.effective_message.delete()
    except Exception:
        pass

    chat_id = update.effective_chat.id

    async def _reply(text):
        msg = await context.bot.send_message(chat_id, text, parse_mode="HTML")
        import asyncio
        async def _del():
            await asyncio.sleep(20)
            try:
                await msg.delete()
            except Exception:
                pass
        asyncio.create_task(_del())

    args = context.args or []
    if len(args) < 3:
        await _reply(
            "❌ Использование: <code>/giveach &lt;user_id&gt; &lt;chat_id&gt; &lt;ach_id&gt;</code>\n\n"
            "Пример: <code>/giveach 123456789 -1001234567890 dice_user</code>"
        )
        return

    try:
        target_uid = int(args[0])
        target_cid = int(args[1])
        ach_id     = args[2]
    except ValueError:
        await _reply("❌ user_id и chat_id должны быть числами.")
        return

    from commands.achievements import ACHIEVEMENTS
    from database import grant_achievement

    if ach_id not in ACHIEVEMENTS:
        known = ", ".join(list(ACHIEVEMENTS.keys())[:10]) + "…"
        await _reply(f"❌ Неизвестная ачивка: <code>{ach_id}</code>\nПример известных: {known}")
        return

    granted = grant_achievement(target_uid, target_cid, ach_id)
    ach = ACHIEVEMENTS[ach_id]
    if granted:
        await _reply(f"✅ Ачивка {ach['icon']} <b>{ach['name']}</b> выдана пользователю <code>{target_uid}</code>.")
    else:
        await _reply(f"ℹ️ Пользователь уже имеет ачивку {ach['icon']} <b>{ach['name']}</b>.")


# ── /announce — рассылка в основной чат ──────────────────────────────────────

async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/announce <текст> — отправить объявление в основной чат. Только владелец, только личка."""
    if not _owner_only(update):
        return
    if update.effective_chat.type != "private":
        return

    try:
        await update.effective_message.delete()
    except Exception:
        pass

    chat_id = update.effective_chat.id

    async def _reply(text):
        msg = await context.bot.send_message(chat_id, text, parse_mode="HTML")
        import asyncio
        async def _del():
            await asyncio.sleep(30)
            try:
                await msg.delete()
            except Exception:
                pass
        asyncio.create_task(_del())

    if not context.args:
        await _reply(
            "❌ Укажи текст: <code>/announce Привет всем!</code>\n\n"
            "Для форматирования используй HTML-теги: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>"
        )
        return

    text = " ".join(context.args)
    main_cid = get_main_chat_id()
    if not main_cid:
        await _reply("❌ Основной чат не настроен.")
        return

    try:
        await context.bot.send_message(main_cid, text, parse_mode="HTML")
        await _reply(f"✅ Объявление отправлено в чат <code>{main_cid}</code>.")
    except Exception as e:
        await _reply(f"❌ Ошибка: {e}")
