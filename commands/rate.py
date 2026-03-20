# ==============================================================================
# commands/rate.py — /rate: оценка фото (только в личке → постит в группу)
# ==============================================================================

import hashlib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import save_photo, add_vote, get_photo, close_photo
import config

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

    # Сохраняем маппинг key → photo_id в памяти бота
    context.bot_data[f"rate_key_{key}"] = photo_id

    save_photo(
        photo_id=photo_id,
        message_id=update.message.message_id,
        chat_id=config.CHAT_ID,
        author_id=author.id,
        author_name=author_name,
        anonymous=False,
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
        f"⭐ Итого баллов: {total}\n"
        f"📊 Средняя оценка: {avg} ({votes} голос(ов))"
    )

    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=caption,
        )
    except Exception:
        pass


async def rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Выбор анонимности ─────────────────────────────────────────────────
    if data.startswith("anon_"):
        if data.endswith("_yes"):
            key = data[5:-4]
            anonymous = True
        else:
            key = data[5:-3]
            anonymous = False

        photo_id = context.bot_data.get(f"rate_key_{key}")
        if not photo_id:
            await query.edit_message_text("❌ Сессия устарела. Отправь фото заново.")
            return

        photo_row = get_photo(photo_id)
        if not photo_row:
            await query.edit_message_text("❌ Фото не найдено.")
            return

        caption = "🖼 Анонимное фото" if anonymous else f"🖼 Фото от {photo_row['author_name']}"
        caption += "\n\n⭐ Голосуй от 1 до 10! Голосование идёт 30 минут."

        try:
            sent = await context.bot.send_photo(
                chat_id=config.CHAT_ID,
                photo=photo_id,
                caption=caption,
                reply_markup=_rating_keyboard(key),
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ Не удалось отправить фото в группу.\n"
                f"Убедись, что бот добавлен в группу и CHAT_ID верный.\n"
                f"Ошибка: {e}"
            )
            return

        save_photo(
            photo_id=photo_id,
            message_id=sent.message_id,
            chat_id=config.CHAT_ID,
            author_id=photo_row["author_id"],
            author_name=photo_row["author_name"],
            anonymous=anonymous,
        )

        context.job_queue.run_once(
            _close_rate_voting,
            VOTE_DURATION,
            data={"photo_id": photo_id, "chat_id": config.CHAT_ID, "message_id": sent.message_id},
        )

        await query.edit_message_text(
            "✅ Фото отправлено в группу!\n"
            "Голосование закроется через 30 минут — итоговый счёт появится там."
        )

    # ── Голосование ───────────────────────────────────────────────────────
    elif data.startswith("rate_"):
        parts = data.rsplit("_", 1)
        score = int(parts[1])
        key = parts[0][5:]  # убираем "rate_"

        photo_id = context.bot_data.get(f"rate_key_{key}")
        if not photo_id:
            await query.answer("❌ Сессия устарела.", show_alert=True)
            return

        photo_row = get_photo(photo_id)
        if not photo_row:
            await query.answer("❌ Фото не найдено.", show_alert=True)
            return

        if photo_row["closed"]:
            await query.answer("⏰ Голосование уже завершено!", show_alert=True)
            return

        voter_id = query.from_user.id
        if voter_id == photo_row["author_id"] and not photo_row["anonymous"]:
            await query.answer("🚫 Нельзя голосовать за своё фото!", show_alert=True)
            return

        avg, votes = add_vote(photo_id, voter_id, score)

        caption = "🖼 Анонимное фото" if photo_row["anonymous"] else f"🖼 Фото от {photo_row['author_name']}"
        caption += (
            f"\n\n⭐ Голосуй от 1 до 10! Голосование идёт 30 минут.\n"
            f"📊 Сейчас: средняя {avg} ({votes} голос(ов))"
        )

        await query.edit_message_caption(
            caption=caption,
            reply_markup=_rating_keyboard(key),
        )
