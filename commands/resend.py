# ==============================================================================
# commands/resend.py — /resend: владелец пишет сообщение от имени бота в группу
# Работает ТОЛЬКО в личке. В списке команд не отображается.
# ==============================================================================

import logging
from telegram import Update
from telegram.ext import ContextTypes
from database import track_bot_message
import config

logger = logging.getLogger(__name__)

# user_id → chat_id куда нужно отправить сообщение
_RESEND_WAITING: dict[int, int] = {}

# user_id → message_id промпта (для удаления после отправки)
_RESEND_PROMPT_MSG: dict[int, int] = {}


async def resend_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик /resend в личке. Только для владельца бота."""
    if update.effective_user.id != config.OWNER_ID:
        return

    # Определяем целевой чат: аргумент или config.CHAT_ID
    target_chat_id = config.CHAT_ID
    if context.args:
        try:
            target_chat_id = int(context.args[0])
        except ValueError:
            pass

    if not target_chat_id:
        await update.message.reply_text(
            "❌ CHAT_ID не настроен.\n"
            "Укажи ID чата вручную: <code>/resend -100xxxxxxxxxx</code>",
            parse_mode="HTML",
        )
        return

    # Удаляем команду из лички
    try:
        await update.message.delete()
    except Exception:
        pass

    user_id = update.effective_user.id
    _RESEND_WAITING[user_id] = target_chat_id

    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"✏️ <b>Режим отправки от имени бота</b>\n\n"
            f"Чат: <code>{target_chat_id}</code>\n\n"
            f"Введи текст сообщения (поддерживается HTML-разметка).\n"
            f"Для отмены напиши /cancel"
        ),
        parse_mode="HTML",
    )
    _RESEND_PROMPT_MSG[user_id] = msg.message_id


async def handle_resend_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Вызывается из bot.py при получении текста в личке.
    Возвращает True если сообщение было обработано как resend.
    """
    if update.effective_chat.type != "private":
        return False

    user_id = update.effective_user.id
    if user_id not in _RESEND_WAITING:
        return False

    # Отмена через /cancel обрабатывается отдельным хэндлером,
    # но на случай если текст "/cancel" попал сюда — выходим
    text = (update.message.text or "").strip()
    if text.lower() in ("/cancel", "/cancel@" + (context.bot.username or "").lower()):
        _RESEND_WAITING.pop(user_id, None)
        _RESEND_PROMPT_MSG.pop(user_id, None)
        return False

    target_chat_id = _RESEND_WAITING.pop(user_id)
    prompt_mid = _RESEND_PROMPT_MSG.pop(user_id, None)

    pm_chat_id = update.effective_chat.id

    try:
        sent = await context.bot.send_message(
            chat_id=target_chat_id,
            text=text,
            parse_mode="HTML",
        )
        track_bot_message(target_chat_id, sent.message_id, text[:80])
        logger.info("resend: отправлено в %s: %s", target_chat_id, text[:60])

        # Удаляем промпт и сообщение с текстом из лички
        for mid in filter(None, [prompt_mid, update.message.message_id]):
            try:
                await context.bot.delete_message(pm_chat_id, mid)
            except Exception:
                pass

        # Кратко подтверждаем, потом убираем
        confirm = await context.bot.send_message(
            chat_id=pm_chat_id,
            text="✅ Отправлено!",
        )
        confirm_id = confirm.message_id

        async def _del_confirm(ctx):
            try:
                await ctx.bot.delete_message(pm_chat_id, confirm_id)
            except Exception:
                pass

        context.job_queue.run_once(_del_confirm, 3)

    except Exception as e:
        logger.error("resend: ошибка отправки в %s: %s", target_chat_id, e)
        await context.bot.send_message(
            chat_id=pm_chat_id,
            text=f"❌ Не удалось отправить: <code>{e}</code>",
            parse_mode="HTML",
        )

    return True


async def resend_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменяет ожидание текста для /resend."""
    user_id = update.effective_user.id
    if user_id not in _RESEND_WAITING:
        return

    _RESEND_WAITING.pop(user_id)
    prompt_mid = _RESEND_PROMPT_MSG.pop(user_id, None)

    # Удаляем промпт и саму команду /cancel
    pm_chat_id = update.effective_chat.id
    for mid in filter(None, [prompt_mid, update.message.message_id]):
        try:
            await context.bot.delete_message(pm_chat_id, mid)
        except Exception:
            pass

    msg = await context.bot.send_message(
        chat_id=pm_chat_id,
        text="❌ Отмена отправки.",
    )
    mid = msg.message_id

    async def _del(ctx):
        try:
            await ctx.bot.delete_message(pm_chat_id, mid)
        except Exception:
            pass

    context.job_queue.run_once(_del, 3)
