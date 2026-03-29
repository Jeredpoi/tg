# ==============================================================================
# commands/anon.py — Команда /anon: анонимное сообщение в группу
# ==============================================================================

import html
import time
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import Forbidden
from chat_config import is_main_chat

logger = logging.getLogger(__name__)

# user_id -> (chat_id, timestamp)
_pending: dict[int, tuple[int, float]] = {}

ANON_TIMEOUT = 300  # 5 минут на ввод сообщения


async def anon_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/anon в группе — просит написать анонимное сообщение в личку боту."""
    user = update.effective_user
    chat = update.effective_chat

    # Удаляем команду из чата
    try:
        await update.message.delete()
    except Exception:
        pass

    # Блокируем в тестовой группе
    if not is_main_chat(chat.id):
        try:
            msg = await context.bot.send_message(
                chat.id,
                "❌ /anon работает только в основной группе.",
                disable_notification=True,
            )
            async def _del(ctx):
                try:
                    await ctx.bot.delete_message(chat.id, msg.message_id)
                except Exception:
                    pass
            context.job_queue.run_once(_del, 5)
        except Exception:
            pass
        return

    # Сохраняем ожидание
    _pending[user.id] = (chat.id, time.time())

    bot_username = context.bot.username

    try:
        await context.bot.send_message(
            user.id,
            f"🎭 <b>Анонимное сообщение</b>\n\n"
            f"Напиши сообщение, и я отправлю его в группу без указания твоего имени.\n\n"
            f"<i>У тебя есть 5 минут. Отправь /cancel для отмены.</i>",
            parse_mode="HTML",
        )
    except Forbidden:
        # Бот не может написать пользователю — он не начал диалог
        del _pending[user.id]
        try:
            display = f"@{user.username}" if user.username else html.escape(user.first_name or "")
            msg = await context.bot.send_message(
                chat.id,
                f"{display}, сначала напиши мне в личку — "
                f"<a href=\"https://t.me/{bot_username}\">@{bot_username}</a>, "
                f"нажми Start, потом снова используй /anon.",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            # Удалим подсказку через 15 секунд
            async def _delete_hint(ctx):
                try:
                    await ctx.bot.delete_message(chat.id, msg.message_id)
                except Exception:
                    pass

            context.job_queue.run_once(_delete_hint, 15)
        except Exception:
            pass


async def handle_anon_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cancel в личке — отменяет ожидание анонимного сообщения."""
    user = update.effective_user
    if update.effective_chat.type != "private":
        return
    if user.id in _pending:
        del _pending[user.id]
        await update.message.reply_text("❌ Отменено.")
    else:
        await update.message.reply_text("Нечего отменять.")


async def handle_anon_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Вызывается из обработчика текстовых сообщений в личке.
    Возвращает True, если сообщение было обработано как анонимное.
    """
    user = update.effective_user
    if update.effective_chat.type != "private":
        return False

    pending = _pending.get(user.id)
    if not pending:
        return False

    chat_id, ts = pending

    # Таймаут
    if time.time() - ts > ANON_TIMEOUT:
        del _pending[user.id]
        await update.message.reply_text("⏰ Время вышло. Используй /anon снова в группе.")
        return True

    text = update.message.text or ""
    if not text.strip():
        await update.message.reply_text("❌ Пустое сообщение. Напиши что-нибудь.")
        return True

    del _pending[user.id]

    try:
        await context.bot.send_message(
            chat_id,
            f"🎭 <b>Анонимное сообщение:</b>\n\n{html.escape(text)}",
            parse_mode="HTML",
        )
        await update.message.reply_text("✅ Сообщение отправлено анонимно!")
    except Exception as e:
        logger.exception("anon send failed: %s", e)
        await update.message.reply_text("❌ Не удалось отправить сообщение. Попробуй снова.")

    return True
