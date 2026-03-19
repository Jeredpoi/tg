# ==============================================================================
# commands/coinflip.py — Команда /coinflip
# ==============================================================================

import random
from telegram import Update
from telegram.ext import ContextTypes

RESULTS = [
    ("🦅 Орёл!", "Монетка упала орлом вверх."),
    ("🔵 Решка!", "Монетка упала решкой вверх."),
]


async def coinflip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /coinflip. Бросает монетку."""
    title, desc = random.choice(RESULTS)
    await update.message.reply_text(f"{title}\n{desc}")
