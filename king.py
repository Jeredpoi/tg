# ==============================================================================
# commands/king.py — Команда /king
# ==============================================================================

import random
from telegram import Update
from telegram.ext import ContextTypes
from database import get_all_users


async def king_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /king.
    Случайно выбирает участника из базы и объявляет его королём чата.
    """
    users = get_all_users()

    # Фильтруем только тех у кого есть username
    eligible = [u for u in users if u["username"]]

    if not eligible:
        await update.message.reply_text(
            "😢 В базе нет пользователей с username.\n"
            "Пусть участники чата сначала напишут что-нибудь!"
        )
        return

    winner = random.choice(eligible)
    mention = f"@{winner['username']}"

    text = (
        f"👑 Король чата сегодня — {mention}!\n\n"
        f"Все склоняются перед великим и ужасным {mention}. "
        f"Трон ваш до завтра, не злоупотребляйте властью 😈"
    )

    await update.message.reply_text(text)
