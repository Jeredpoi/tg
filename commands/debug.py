# ==============================================================================
# commands/debug.py — Команда /debug
# Отправляет отладочную информацию о текущем чате и пользователе.
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /debug.
    Удобно использовать для первоначальной настройки: получить CHAT_ID и т.д.
    """
    message = update.message
    chat    = update.effective_chat
    user    = update.effective_user

    if not message or not chat or not user:
        return

    username_display = f"@{user.username}" if user.username else "—"

    text = (
        "🛠 <b>Debug информация</b>\n\n"
        f"<b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"<b>Chat type:</b> {chat.type}\n\n"
        f"<b>User ID:</b> <code>{user.id}</code>\n"
        f"<b>Username:</b> {username_display}\n"
        f"<b>First name:</b> {user.first_name}\n\n"
        f"<b>Message ID:</b> <code>{message.message_id}</code>"
    )

    await message.reply_text(text, parse_mode="HTML")
