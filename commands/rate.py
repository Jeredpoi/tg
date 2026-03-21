# ==============================================================================
# commands/rate.py — /rate: оценка фото (только в личке → постит в группу)
# ==============================================================================

import hashlib
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import save_photo, add_vote, get_photo, get_photo_by_key, close_photo
import config

logger = logging.getLogger(__name__)

VOTE_DURATION = 30 * 60  # 30 минут в секундах


def _short_key(photo_id: str) -> str:
    """Возвращает короткий 8-символьный ключ для callback_data (лимит Telegram — 64 байта)."""
    return hashlib.md5(photo_id.encode()).hexdigest()[:8]


def _rating_keyboard(key: str) -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton(str(i), callback_data=f"rate_{key}_{i}") for i in range(1, 6)]
    row2 = [InlineKeyboardButton(str(i), callback_data=f"rate_{key}_{i}") for i in range(6, 11)]
    return InlineKeyboardMarkup([row1, row2])


def _anon_keyboard(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да, скрыть", callback_data=f"anon_{key}_yes"),
        InlineKeyboardButton("❌ Нет",        callback_data=f"anon_{key}_no"),
    ]])


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "📸 Команда /rate работает только в личных сообщениях!\n"
            "Напиши мне в личку — там отправь фото для оценки группой."
        )
        return

    await update.message.reply_text(
        "📸 Отправь мне фото, которое хочешь выставить на оценку группы.\n"
        "Голосование будет идти 30 минут, затем покажу итоговый счёт."
    )


async def handle_rate_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает любое фото в личке и предлагает выставить на оценку группы."""
    photo = update.message.photo[-1]
    photo_id = photo.file_id
    key = _short_key(photo_id)
    author = update.effective_user
    author_name = f"@{author.username}" if author.username else author.first_name

    save_photo(
        photo_id=photo_id,
        message_id=update.message.message_id,
        chat_id=config.CHAT_ID,
        author_id=author.id,
        author_name=author_name,
        anonymous=False,
        key=key,
    )

    await update.message.reply_text(
        "🤔 Скрыть тебя как автора в группе?",
        reply_markup=_anon_keyboard(key),
    )


async def _close_rate_voting(context) -> None:
    """Job-функция: закрывает голосование через VOTE_DURATION секунд."""
    data = context.job.data
    photo_id = data["photo_id"]
    chat_id = data["chat_id"]
    message_id = data["message_id"]

    close_photo(photo_id)

    photo_row = get_photo(photo_id)
    if not photo_row:
        return

    total = photo_row["total_score"]
    votes = photo_row["vote_count"]
    avg = round(total / votes, 2) if votes > 0 else 0

    caption = "🖼 Анонимное фото" if photo_row["anonymous"] else f"🖼 Фото от {photo_row['author_name']}"
    caption += (
        f"\n\n🏁 Голосование завершено!\n"
        f"⭐ Средняя оценка: {avg} ({votes} голос(ов))"
    )

    try:
        gallery_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("🖼 Галерея", url="https://144.31.75.246.sslip.io")
        ]])
        await context.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=caption,
            reply_markup=gallery_btn,
        )
    except Exception as e:
        logger.error("Не удалось закрыть голосование chat=%s msg=%s: %s", chat_id, message_id, e)


async def rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data

    # ── Выбор анонимности ─────────────────────────────────────────────────
    if data.startswith("anon_"):
        if data.endswith("_yes"):
            key = data[5:-4]
            anonymous = True
        else:
            key = data[5:-3]
            anonymous = False

        # Ищем фото по ключу из БД (не из bot_data!)
        photo_row = get_photo_by_key(key)
        if not photo_row:
            await query.edit_message_text("❌ Фото не найдено. Отправь фото заново.")
            return

        photo_id = photo_row["photo_id"]

        if not config.CHAT_ID:
            await query.edit_message_text(
                "❌ CHAT_ID не настроен.\n"
                "Добавь бота в группу — он автоматически запомнит ID чата."
            )
            return

        caption = "🖼 Анонимное фото" if anonymous else f"🖼 Фото от {photo_row['author_name']}"
        caption += "\n\n⭐ Голосуй от 1 до 10! Голосование идёт 30 минут.\n📊 Сейчас: нет голосов"

        try:
            sent = await context.bot.send_photo(
                chat_id=config.CHAT_ID,
                photo=photo_id,
                caption=caption,
                reply_markup=_rating_keyboard(key),
            )
        except Exception as e:
            logger.error("send_photo failed: chat_id=%s error=%s", config.CHAT_ID, e)
            await query.edit_message_text(
                f"❌ Не удалось отправить фото в группу.\n"
                f"CHAT_ID: <code>{config.CHAT_ID}</code>\n"
                f"Ошибка: <code>{e}</code>\n\n"
                f"Проверь: бот добавлен в группу? Напиши /debug в группе.",
                parse_mode="HTML",
            )
            return

        # Сообщаем пользователю сразу — до любых операций с БД/job_queue
        await query.edit_message_text(
            "✅ Фото отправлено в группу!\n"
            "Голосование закроется через 30 минут — итог появится там."
        )

        save_photo(
            photo_id=photo_id,
            message_id=sent.message_id,
            chat_id=config.CHAT_ID,
            author_id=photo_row["author_id"],
            author_name=photo_row["author_name"],
            anonymous=anonymous,
            key=key,
        )

        context.job_queue.run_once(
            _close_rate_voting,
            VOTE_DURATION,
            data={"photo_id": photo_id, "chat_id": config.CHAT_ID, "message_id": sent.message_id},
        )

    # ── Голосование ───────────────────────────────────────────────────────
    elif data.startswith("rate_"):
        parts = data.rsplit("_", 1)
        score = int(parts[1])
        key = parts[0][5:]  # убираем "rate_"

        # Ищем по ключу из БД
        photo_row = get_photo_by_key(key)
        if not photo_row:
            await query.answer("❌ Фото не найдено.", show_alert=True)
            return

        photo_id = photo_row["photo_id"]

        if photo_row["closed"]:
            await query.answer("⏰ Голосование уже завершено!", show_alert=True)
            return

        voter_id = query.from_user.id
        # Блокируем автора только в публичном режиме
        if voter_id == photo_row["author_id"] and not photo_row["anonymous"]:
            await query.answer("🚫 Нельзя голосовать за своё фото!", show_alert=True)
            return

        avg, votes = add_vote(photo_id, voter_id, score)

        caption = "🖼 Анонимное фото" if photo_row["anonymous"] else f"🖼 Фото от {photo_row['author_name']}"
        caption += (
            f"\n\n⭐ Голосуй от 1 до 10! Голосование идёт 30 минут.\n"
            f"📊 Сейчас: средняя {avg} ({votes} голос(ов))"
        )

        await query.answer(f"Вы поставили {score} ⭐")
        try:
            await query.edit_message_caption(
                caption=caption,
                reply_markup=_rating_keyboard(key),
            )
        except Exception as e:
            logger.warning("edit_message_caption: %s", e)
