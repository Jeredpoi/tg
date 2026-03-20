# ==============================================================================
# commands/rate.py — /rate: оценка фото (только в личке → постит в группу)
# ==============================================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import save_photo, add_vote, get_photo, close_photo
from config import CHAT_ID

VOTE_DURATION = 30 * 60  # 30 минут в секундах


def _rating_keyboard(photo_id: str) -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton(str(i), callback_data=f"rate_{photo_id}_{i}") for i in range(1, 6)]
    row2 = [InlineKeyboardButton(str(i), callback_data=f"rate_{photo_id}_{i}") for i in range(6, 11)]
    return InlineKeyboardMarkup([row1, row2])


def _anon_keyboard(photo_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да, скрыть", callback_data=f"anon_{photo_id}_yes"),
        InlineKeyboardButton("❌ Нет",        callback_data=f"anon_{photo_id}_no"),
    ]])


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /rate — только в личных сообщениях.
    Просит прислать фото, затем отправляет его в группу с голосованием на 30 минут.
    """
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "📸 Команда /rate работает только в личных сообщениях!\n"
            "Напиши мне в личку — там отправь фото для оценки группой."
        )
        return

    context.user_data["awaiting_rate_photo"] = True
    await update.message.reply_text(
        "📸 Отправь мне фото, которое хочешь выставить на оценку группы.\n"
        "Голосование будет идти 30 минут, затем покажу итоговый счёт."
    )


async def handle_rate_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Принимает фото в личке (после /rate или напрямую).
    Зарегистрирован как MessageHandler(PHOTO & ChatType.PRIVATE) в bot.py.
    """
    context.user_data.pop("awaiting_rate_photo", None)

    photo = update.message.photo[-1]  # максимальное разрешение
    photo_id = photo.file_id
    author = update.effective_user
    author_name = f"@{author.username}" if author.username else author.first_name

    # Сохраняем предварительно (chat_id группы укажем позже)
    save_photo(
        photo_id=photo_id,
        message_id=update.message.message_id,
        chat_id=CHAT_ID,
        author_id=author.id,
        author_name=author_name,
        anonymous=False,
    )

    await update.message.reply_text(
        "🤔 Скрыть тебя как автора в группе?",
        reply_markup=_anon_keyboard(photo_id),
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
        pass  # Сообщение могло быть удалено


async def rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик callback-кнопок:
      anon_{photo_id}_yes / anon_{photo_id}_no  — выбор анонимности (в личке)
      rate_{photo_id}_{score}                   — голосование (в группе)
    """
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Выбор анонимности (приходит из лички) ─────────────────────────────
    if data.startswith("anon_"):
        if data.endswith("_yes"):
            photo_id = data[5:-4]
            anonymous = True
        else:
            photo_id = data[5:-3]
            anonymous = False

        photo_row = get_photo(photo_id)
        if not photo_row:
            await query.edit_message_text("❌ Фото не найдено.")
            return

        caption = "🖼 Анонимное фото" if anonymous else f"🖼 Фото от {photo_row['author_name']}"
        caption += "\n\n⭐ Голосуй от 1 до 10! Голосование идёт 30 минут."

        # Отправляем фото в группу
        sent = await context.bot.send_photo(
            chat_id=CHAT_ID,
            photo=photo_id,
            caption=caption,
            reply_markup=_rating_keyboard(photo_id),
        )

        # Обновляем запись: сохраняем message_id группового сообщения
        save_photo(
            photo_id=photo_id,
            message_id=sent.message_id,
            chat_id=CHAT_ID,
            author_id=photo_row["author_id"],
            author_name=photo_row["author_name"],
            anonymous=anonymous,
        )

        # Планируем закрытие голосования через 30 минут
        context.job_queue.run_once(
            _close_rate_voting,
            VOTE_DURATION,
            data={"photo_id": photo_id, "chat_id": CHAT_ID, "message_id": sent.message_id},
        )

        await query.edit_message_text(
            "✅ Фото отправлено в группу!\n"
            "Голосование закроется через 30 минут — итоговый счёт появится там."
        )

    # ── Голосование (приходит из группы) ─────────────────────────────────
    elif data.startswith("rate_"):
        parts = data.rsplit("_", 1)         # ["rate_{photo_id}", "{score}"]
        score = int(parts[1])
        photo_id = parts[0][5:]             # убираем "rate_"

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
            reply_markup=_rating_keyboard(photo_id),
        )
