# ==============================================================================
# commands/botset.py — /botset: кастомизация бота (аватар, описание, имя)
# Только владелец, только личка.
# ==============================================================================

import json
import logging
import os
import datetime

from telegram import Update
from telegram.ext import ContextTypes
from config import OWNER_ID

logger = logging.getLogger(__name__)

_IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "..", "bot_identity.json")
_BOTSET_PHOTO_STATE = "botset_photo"  # ключ в context.user_data


def _load_identity() -> dict:
    try:
        with open(_IDENTITY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_identity(data: dict) -> None:
    with open(_IDENTITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def render_template(template: str, online: bool = True) -> str:
    """Подставляет переменные в шаблон описания."""
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    status = "🟢 Онлайн" if online else "🔴 Оффлайн"
    version = now.strftime("%Y.%m")
    return (
        template
        .replace("{status}", status)
        .replace("{version}", version)
        .replace("{date}", now.strftime("%d.%m.%Y"))
    )


async def apply_identity(bot, online: bool = True) -> None:
    """Применяет сохранённые шаблоны описания/имени к боту. Вызывается при старте и остановке."""
    identity = _load_identity()
    if not identity:
        return

    if desc := identity.get("desc"):
        try:
            await bot.set_my_description(render_template(desc, online))
        except Exception as e:
            logger.warning("botset: не удалось установить описание: %s", e)

    if short := identity.get("short_desc"):
        try:
            await bot.set_my_short_description(render_template(short, online))
        except Exception as e:
            logger.warning("botset: не удалось установить короткое описание: %s", e)

    if name := identity.get("name"):
        try:
            await bot.set_my_name(name)
        except Exception as e:
            logger.warning("botset: не удалось установить имя: %s", e)


async def botset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/botset — кастомизация бота. Только владелец, только личка."""
    if update.effective_user.id != OWNER_ID:
        return
    if update.effective_chat.type != "private":
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    args = context.args or []

    # /botset без аргументов — показать меню
    if not args:
        identity = _load_identity()
        desc       = identity.get("desc", "—")
        short_desc = identity.get("short_desc", "—")
        name       = identity.get("name", "—")
        await update.message.reply_text(
            "🤖 <b>Кастомизация бота</b>\n\n"
            f"<b>Имя:</b> {name}\n"
            f"<b>Описание:</b> {desc}\n"
            f"<b>Короткое описание:</b> {short_desc}\n\n"
            "<b>Команды:</b>\n"
            "/botset name &lt;текст&gt; — имя бота\n"
            "/botset desc &lt;текст&gt; — описание (есть переменные)\n"
            "/botset shortdesc &lt;текст&gt; — короткое описание\n"
            "/botset photo — установить аватар (следующее фото)\n"
            "/botset apply — применить сохранённые шаблоны прямо сейчас\n\n"
            "<b>Переменные в описании:</b>\n"
            "<code>{status}</code> — 🟢 Онлайн / 🔴 Оффлайн\n"
            "<code>{version}</code> — год.месяц (2025.04)\n"
            "<code>{date}</code> — текущая дата",
            parse_mode="HTML",
        )
        return

    sub = args[0].lower()

    # /botset name <текст>
    if sub == "name":
        if len(args) < 2:
            await update.message.reply_text("❌ Укажи имя: /botset name Скаут")
            return
        new_name = " ".join(args[1:])
        if len(new_name) > 64:
            await update.message.reply_text("❌ Имя слишком длинное (макс. 64 символа).")
            return
        try:
            await context.bot.set_my_name(new_name)
            identity = _load_identity()
            identity["name"] = new_name
            _save_identity(identity)
            await update.message.reply_text(f"✅ Имя бота изменено на: <b>{new_name}</b>", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    # /botset desc <текст>
    elif sub == "desc":
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Укажи описание: /botset desc Бот онлайн: {status}\n\n"
                "Переменные: {status}, {version}, {date}"
            )
            return
        template = " ".join(args[1:])
        if len(template) > 512:
            await update.message.reply_text("❌ Описание слишком длинное (макс. 512 символов).")
            return
        rendered = render_template(template, online=True)
        try:
            await context.bot.set_my_description(rendered)
            identity = _load_identity()
            identity["desc"] = template
            _save_identity(identity)
            await update.message.reply_text(
                f"✅ Описание обновлено.\n\n<b>Шаблон:</b> {template}\n<b>Сейчас выглядит:</b> {rendered}",
                parse_mode="HTML",
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    # /botset shortdesc <текст>
    elif sub == "shortdesc":
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Укажи короткое описание: /botset shortdesc Скаут на связи {status}"
            )
            return
        template = " ".join(args[1:])
        if len(template) > 120:
            await update.message.reply_text("❌ Слишком длинное (макс. 120 символов).")
            return
        rendered = render_template(template, online=True)
        try:
            await context.bot.set_my_short_description(rendered)
            identity = _load_identity()
            identity["short_desc"] = template
            _save_identity(identity)
            await update.message.reply_text(
                f"✅ Короткое описание обновлено.\n<b>Сейчас:</b> {rendered}",
                parse_mode="HTML",
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    # /botset photo — ждём следующее фото
    elif sub == "photo":
        context.user_data[_BOTSET_PHOTO_STATE] = True
        await update.message.reply_text(
            "📸 Жду фото для аватара бота.\n"
            "Отправь фотографию следующим сообщением."
        )

    # /botset apply — применить шаблоны
    elif sub == "apply":
        await apply_identity(context.bot, online=True)
        await update.message.reply_text("✅ Шаблоны применены.")

    else:
        await update.message.reply_text(
            f"❌ Неизвестная подкоманда: <code>{sub}</code>\n"
            "Доступные: name, desc, shortdesc, photo, apply",
            parse_mode="HTML",
        )


async def handle_botset_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Обработчик фото для установки аватара.
    Вызывается из _maybe_token_reply в личке.
    Возвращает True если сообщение обработано.
    """
    if update.effective_user.id != OWNER_ID:
        return False
    if not context.user_data.get(_BOTSET_PHOTO_STATE):
        return False
    if not update.message or not update.message.photo:
        return False

    context.user_data.pop(_BOTSET_PHOTO_STATE, None)

    photo = update.message.photo[-1]  # наибольшее разрешение
    try:
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        import io
        await context.bot.set_my_profile_photo(io.BytesIO(bytes(photo_bytes)))
        await update.message.reply_text("✅ Аватар бота обновлён!")
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось установить аватар: {e}")
    return True
