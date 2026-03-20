# ==============================================================================
# commands/eightball.py — Команда /8ball
# ==============================================================================

import random
from telegram import Update
from telegram.ext import ContextTypes

EIGHTBALL_RESPONSES = [
    # Позитивные
    "Бесспорно ✅",
    "Предрешено ✅",
    "Никаких сомнений ✅",
    "Определённо да ✅",
    "Можешь быть уверен ✅",
    "Мне кажется — да 🟢",
    "Вероятнее всего 🟢",
    "Хорошие перспективы 🟢",
    "Знаки говорят — да 🟢",
    "Всё идёт к тому 🟢",
    # Нейтральные
    "Пока не ясно 🔮",
    "Спроси позже 🔮",
    "Лучше не рассказывать 🔮",
    "Сейчас нельзя предсказать 🔮",
    "Сосредоточься и спроси снова 🔮",
    "Шансы 50 на 50 🎲",
    # Негативные
    "Не рассчитывай на это ❌",
    "Мой ответ — нет ❌",
    "По моим данным — нет ❌",
    "Перспективы не очень ❌",
    "Весьма сомнительно ❌",
    "Точно нет ❌",
]


async def eightball_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /8ball <вопрос>."""
    if not context.args:
        await update.message.reply_text(
            "🎱 Задай мне вопрос!\nПример: /8ball Будет ли сегодня дождь?"
        )
        return

    question = " ".join(context.args)
    answer = random.choice(EIGHTBALL_RESPONSES)

    await update.message.reply_text(
        f"🎱 <b>Вопрос:</b> {question}\n\n<b>Ответ:</b> {answer}",
        parse_mode="HTML",
    )
