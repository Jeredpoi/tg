# ==============================================================================
# commands/modtools.py — Утилиты для владельца бота
# /synccmds, /giveach, /announce
# ==============================================================================

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes
from config import OWNER_ID
from chat_config import sync_bot_commands, get_main_chat_id

logger = logging.getLogger(__name__)


def _owner_only(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == OWNER_ID


async def _autodel_reply(context, chat_id: int, text: str, delay: int = 20) -> None:
    """Отправляет сообщение и удаляет его через delay секунд."""
    msg = await context.bot.send_message(chat_id, text, parse_mode="HTML")

    async def _del():
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except Exception:
            pass

    asyncio.create_task(_del())


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
        await _autodel_reply(
            context,
            update.effective_chat.id,
            "✅ Команды синхронизированы с Bot Father!\n\n"
            "<i>Список команд в Telegram обновлён.</i>",
        )
    except Exception as e:
        await _autodel_reply(context, update.effective_chat.id, f"❌ Ошибка синхронизации: {e}")


# ── /giveach — вручную выдать ачивку пользователю ────────────────────────────

async def giveach_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/giveach <user_id> <chat_id> <ach_id> — вручную выдать ачивку. Только владелец, только личка."""
    if not _owner_only(update):
        return

    try:
        await update.effective_message.delete()
    except Exception:
        pass

    chat_id = update.effective_chat.id

    args = context.args or []
    if len(args) < 3:
        await _autodel_reply(
            context, chat_id,
            "❌ Использование:\n"
            "<code>/giveach &lt;user_id&gt; &lt;chat_id&gt; &lt;ach_id&gt;</code>\n\n"
            "Пример:\n"
            "<code>/giveach 123456789 -1001234567890 dice_user</code>",
            delay=30,
        )
        return

    try:
        target_uid = int(args[0])
        target_cid = int(args[1])
        ach_id     = args[2]
    except ValueError:
        await _autodel_reply(context, chat_id, "❌ user_id и chat_id должны быть числами.")
        return

    from commands.achievements import ACHIEVEMENTS
    from database import grant_achievement

    if ach_id not in ACHIEVEMENTS:
        await _autodel_reply(
            context, chat_id,
            f"❌ Неизвестная ачивка: <code>{ach_id}</code>",
        )
        return

    granted = grant_achievement(target_uid, target_cid, ach_id)
    ach = ACHIEVEMENTS[ach_id]
    if granted:
        await _autodel_reply(
            context, chat_id,
            f"✅ Ачивка {ach['icon']} <b>{ach['name']}</b> выдана пользователю <code>{target_uid}</code>.",
        )
    else:
        await _autodel_reply(
            context, chat_id,
            f"ℹ️ Пользователь уже имеет ачивку {ach['icon']} <b>{ach['name']}</b>.",
        )


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

    if not context.args:
        await _autodel_reply(
            context, chat_id,
            "❌ Укажи текст: <code>/announce Привет всем!</code>\n"
            "Поддерживаются HTML-теги: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>",
        )
        return

    text     = " ".join(context.args)
    main_cid = get_main_chat_id()
    if not main_cid:
        await _autodel_reply(context, chat_id, "❌ Основной чат не настроен.")
        return

    try:
        await context.bot.send_message(main_cid, text, parse_mode="HTML")
        await _autodel_reply(context, chat_id, f"✅ Объявление отправлено.")
    except Exception as e:
        await _autodel_reply(context, chat_id, f"❌ Ошибка: {e}")
