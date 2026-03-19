# ==============================================================================
# commands/debug.py — Команда /debug
# Отправляет отладочную информацию о текущем чате и пользователе.
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /debug.

    Собирает и отправляет диагностическую информацию:
      - Chat ID и тип чата
      - User ID, username и имя пользователя
      - ID текущего сообщения

    Удобно использовать для первоначальной настройки бота:
    получить CHAT_ID, проверить, что бот видит нужный чат и т.д.
    """
    message = update.message
    chat    = update.effective_chat
    user    = update.effective_user

    # Защита от случаев когда объекты отсутствуют (edge-case)
    if not message or not chat or not user:
        return

    # Username может отсутствовать — показываем заглушку
    username_display = f"@{user.username}" if user.username else "—"

    # Формируем читаемое сообщение в формате HTML
    text = (
        "🛠 <b>Debug информация</b>\n"
        "\n"
        f"<b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"<b>Chat type:</b> {chat.type}\n"
        "\n"
        f"<b>User ID:</b> <code>{user.id}</code>\n"
        f"<b>Username:</b> {username_display}\n"
        f"<b>First name:</b> {user.first_name}\n"
        "\n"
        f"<b>Message ID:</b> <code>{message.message_id}</code>"
    )

    await message.reply_text(text, parse_mode="HTML")
