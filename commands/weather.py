# ==============================================================================
# commands/weather.py — Команда /weather
# Использует wttr.in — бесплатный API без ключа.
# ==============================================================================

import urllib.parse
import httpx
from telegram import Update
from telegram.ext import ContextTypes


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /weather <город>.
    Пример: /weather Москва
    """
    if not context.args:
        await update.message.reply_text(
            "🌤 Укажи город!\nПример: /weather Москва"
        )
        return

    city = " ".join(context.args)
    city_encoded = urllib.parse.quote(city)

    try:
        url = f"https://wttr.in/{city_encoded}?format=3&lang=ru"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url, headers={"User-Agent": "curl/7.68.0"})
            result = resp.text.strip()

        if not result:
            raise ValueError("Пустой ответ")

        await update.message.reply_text(f"🌤 {result}")

    except Exception:
        await update.message.reply_text(
            f"❌ Не удалось получить погоду для «{city}».\n"
            "Проверь название города и попробуй ещё раз."
        )
