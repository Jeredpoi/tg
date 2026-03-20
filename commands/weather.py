# ==============================================================================
# commands/weather.py — Команда /weather (Яндекс.Погода API)
# ==============================================================================

import logging

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import YANDEX_WEATHER_KEY

logger = logging.getLogger(__name__)

CONDITION_MAP = {
    "clear":                    ("☀️",  "Ясно"),
    "partly-cloudy":            ("🌤",  "Малооблачно"),
    "cloudy":                   ("⛅",  "Облачно"),
    "overcast":                 ("☁️",  "Пасмурно"),
    "drizzle":                  ("🌦",  "Морось"),
    "light-rain":               ("🌧",  "Небольшой дождь"),
    "rain":                     ("🌧",  "Дождь"),
    "moderate-rain":            ("🌧",  "Умеренный дождь"),
    "heavy-rain":               ("🌧",  "Сильный дождь"),
    "continuous-heavy-rain":    ("⛈",  "Непрерывный ливень"),
    "showers":                  ("🌦",  "Ливень"),
    "wet-snow":                 ("🌨",  "Дождь со снегом"),
    "light-snow":               ("❄️",  "Небольшой снег"),
    "snow":                     ("❄️",  "Снег"),
    "snow-showers":             ("🌨",  "Снегопад"),
    "hail":                     ("🌩",  "Град"),
    "thunderstorm":             ("⛈",  "Гроза"),
    "thunderstorm-with-rain":   ("⛈",  "Гроза с дождём"),
    "thunderstorm-with-hail":   ("⛈",  "Гроза с градом"),
}

WIND_DIR_MAP = {
    "nw": "С-З ↖", "n": "С ↑", "ne": "С-В ↗", "e": "В →",
    "se": "Ю-В ↘", "s": "Ю ↓", "sw": "Ю-З ↙", "w": "З ←",
    "c":  "Штиль",
}


def _cond(code: str) -> tuple[str, str]:
    return CONDITION_MAP.get(code, ("🌡", code))


def _sign(t: int | float) -> str:
    return f"+{t}" if t > 0 else str(t)


async def _geocode(city: str) -> tuple[float, float, str] | None:
    """Геокодирование через Nominatim (OpenStreetMap), возвращает (lat, lon, display_name)."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city, "format": "json", "limit": 1, "accept-language": "ru"}
    headers = {"User-Agent": "TelegramBot/1.0"}
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(url, params=params, headers=headers)
        data = resp.json()
    if not data:
        return None
    item = data[0]
    # Берём только первую часть display_name (до первой запятой)
    name = item.get("display_name", city).split(",")[0].strip()
    return float(item["lat"]), float(item["lon"]), name


async def _fetch_weather(lat: float, lon: float) -> dict:
    """Запрашивает погоду с Яндекс.Погода API."""
    url = "https://api.weather.yandex.ru/v2/forecast"
    params = {"lat": lat, "lon": lon, "limit": 4, "hours": "true", "extra": "false", "lang": "ru_RU"}
    headers = {"X-Yandex-Weather-Key": YANDEX_WEATHER_KEY}
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _build_current_text(city_name: str, data: dict) -> str:
    fact = data["fact"]
    temp = fact.get("temp", "?")
    feels = fact.get("feels_like", "?")
    cond_code = fact.get("condition", "")
    icon, cond_name = _cond(cond_code)
    wind_speed = fact.get("wind_speed", "?")
    wind_dir = WIND_DIR_MAP.get(fact.get("wind_dir", ""), fact.get("wind_dir", ""))
    humidity = fact.get("humidity", "?")
    pressure = fact.get("pressure_mm", "?")

    lines = [
        f"{icon} <b>Погода в {city_name}</b>",
        "─" * 22,
        f"🌡 <b>Температура:</b> {_sign(temp)}°C  (ощущается {_sign(feels)}°C)",
        f"{icon} <b>Состояние:</b> {cond_name}",
        f"💨 <b>Ветер:</b> {wind_dir}, {wind_speed} м/с",
        f"💧 <b>Влажность:</b> {humidity}%",
        f"🔍 <b>Давление:</b> {pressure} мм рт.ст.",
    ]
    return "\n".join(lines)


def _build_forecast_text(city_name: str, data: dict) -> str:
    forecasts = data.get("forecasts", [])[:4]
    lines = [f"📅 <b>Прогноз для {city_name}</b>", "─" * 22]
    for day in forecasts:
        date = day.get("date", "")
        parts = day.get("parts", {})
        # Берём день
        d = parts.get("day_short") or parts.get("day") or {}
        temp_min = day.get("parts", {}).get("night_short", {}).get("temp_min")
        temp_max = d.get("temp_max", d.get("temp"))
        cond_code = d.get("condition", "")
        icon, cond_name = _cond(cond_code)
        t_min = _sign(temp_min) if isinstance(temp_min, (int, float)) else "?"
        t_max = _sign(temp_max) if isinstance(temp_max, (int, float)) else "?"
        lines.append(f"📆 <b>{date}</b>  {icon} {cond_name}  {t_min}…{t_max}°C")
    return "\n".join(lines)


def _keyboard(lat: float, lon: float, city_name: str) -> InlineKeyboardMarkup:
    # Ограничиваем название города до 20 символов для callback_data
    short = city_name[:20]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Прогноз на 4 дня", callback_data=f"wforecast:{lat:.4f}:{lon:.4f}:{short}"),
            InlineKeyboardButton("🔄 Обновить",         callback_data=f"wrefresh:{lat:.4f}:{lon:.4f}:{short}"),
        ]
    ])


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /weather <город>."""
    if not context.args:
        await update.message.reply_text(
            "🌤 Укажи город!\nПример: /weather Москва"
        )
        return

    city = " ".join(context.args)

    msg = await update.message.reply_text("⏳ Получаю погоду...")

    try:
        geo = await _geocode(city)
        if geo is None:
            await msg.edit_text(f"❌ Не могу найти город «{city}». Проверь название.")
            return

        lat, lon, city_name = geo
        data = await _fetch_weather(lat, lon)
        text = _build_current_text(city_name, data)
        kb = _keyboard(lat, lon, city_name)
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)

    except Exception as e:
        logger.exception("weather_command failed for city=%r: %s", city, e)
        await msg.edit_text(
            f"❌ Не удалось получить погоду для «{city}».\n"
            f"Ошибка: <code>{e}</code>",
            parse_mode="HTML",
        )


async def weather_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик inline-кнопок прогноза и обновления."""
    query = update.callback_query
    await query.answer()

    data = query.data  # "wforecast:lat:lon:city" или "wrefresh:lat:lon:city"
    parts = data.split(":", 3)
    if len(parts) != 4:
        return

    action, lat_s, lon_s, city_name = parts
    try:
        lat, lon = float(lat_s), float(lon_s)
    except ValueError:
        return

    try:
        weather_data = await _fetch_weather(lat, lon)
        kb = _keyboard(lat, lon, city_name)

        if action == "wforecast":
            text = _build_forecast_text(city_name, weather_data)
        else:  # wrefresh
            text = _build_current_text(city_name, weather_data)

        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.answer("Погода не изменилась 🔄")
            else:
                raise

    except BadRequest:
        raise
    except Exception as e:
        logger.exception("weather_callback failed city=%r action=%r: %s", city_name, action, e)
        try:
            await query.edit_message_text(
                f"❌ Не удалось получить погоду для «{city_name}».\n"
                f"Ошибка: <code>{e}</code>",
                parse_mode="HTML",
                reply_markup=_keyboard(lat, lon, city_name),
            )
        except BadRequest:
            pass
