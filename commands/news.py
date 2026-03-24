# ==============================================================================
# commands/news.py — Команда /news: писать в группу от лица бота (только владелец)
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes
from config import CHAT_ID, OWNER_ID


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /news <текст> — отправляет сообщение в группу от имени бота.
    Работает только в личке и только для владельца (OWNER_ID).
    """
    user = update.effective_user

    if user.id != OWNER_ID:
        return  # тихо игнорируем чужих

    text = " ".join(context.args) if context.args else ""
    if not text.strip():
        await update.message.reply_text("Напиши текст после команды:\n/news Привет всем!")
        return

    await context.bot.send_message(CHAT_ID, text)
    await update.message.reply_text("✅ Отправлено.")


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/myid — показывает твой Telegram User ID (личка)."""
    user = update.effective_user
    await update.message.reply_text(
        f"Твой <b>User ID</b>: <code>{user.id}</code>\n\n"
        f"Вставь это число в <code>config.py</code> → <code>OWNER_ID = {user.id}</code>",
        parse_mode="HTML",
    )
