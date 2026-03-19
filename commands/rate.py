# ==============================================================================
# commands/rate.py — Система оценки фото
# ==============================================================================

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import ContextTypes
from database import save_photo, add_vote, get_photo


def _rating_keyboard(photo_id: str) -> InlineKeyboardMarkup:
    """Строит клавиатуру оценок 1–10 для фото."""
    row1 = [InlineKeyboardButton(str(i), callback_data=f"rate_{photo_id}_{i}") for i in range(1, 6)]
    row2 = [InlineKeyboardButton(str(i), callback_data=f"rate_{photo_id}_{i}") for i in range(6, 11)]
    return InlineKeyboardMarkup([row1, row2])


def _anon_keyboard(photo_id: str) -> InlineKeyboardMarkup:
    """Строит клавиатуру выбора анонимности."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да, скрыть", callback_data=f"anon_{photo_id}_yes"),
        InlineKeyboardButton("❌ Нет", callback_data=f"anon_{photo_id}_no"),
    ]])


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /rate.
    Пользователь должен ответить на фото командой /rate.
    Бот спрашивает: скрыть автора?
    """
    message = update.message

    # Проверяем что команда — ответ на сообщение с фото
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text(
            "📸 Ответь командой /rate на фотографию, которую хочешь оценить."
        )
        return

    replied = message.reply_to_message
    photo = replied.photo[-1]  # Берём наибольшее разрешение
    photo_id = photo.file_id

    # Автор фото
    author = replied.from_user
    author_name = f"@{author.username}" if author.username else author.first_name

    # Сохраняем фото в базу (без анонимности — уточним позже)
    save_photo(
        photo_id=photo_id,
        message_id=replied.message_id,
        chat_id=message.chat_id,
        author_id=author.id,
        author_name=author_name,
        anonymous=False,
    )

    # Спрашиваем про анонимность
    await message.reply_text(
        f"🤔 Скрыть автора фото ({author_name})?",
        reply_markup=_anon_keyboard(photo_id),
    )


async def rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик всех callback-кнопок в системе оценки фото.
    Обрабатывает:
      - anon_{photo_id}_yes / anon_{photo_id}_no  — выбор анонимности
      - rate_{photo_id}_{score}                   — голосование
    """
    query = update.callback_query
    await query.answer()

    data = query.data

    # ------------------------------------------------------------------
    # Выбор анонимности
    # ------------------------------------------------------------------
    if data.startswith("anon_"):
        parts = data.split("_", 2)          # ["anon", photo_id, "yes"/"no"]
        photo_id = parts[1]
        choice = parts[2]                   # "yes" или "no"

        photo_row = get_photo(photo_id)
        if not photo_row:
            await query.edit_message_text("❌ Фото не найдено в базе.")
            return

        anonymous = (choice == "yes")
        caption = "🖼 Анонимное фото" if anonymous else f"🖼 Фото от {photo_row['author_name']}"

        # Пересылаем фото с нужной подписью
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo_id,
            caption=f"{caption}\n\n⭐ Средняя оценка: нет голосов",
            reply_markup=_rating_keyboard(photo_id),
        )

        # Обновляем флаг анонимности в базе
        # (save_photo с тем же photo_id перезапишет запись)
        save_photo(
            photo_id=photo_id,
            message_id=photo_row["message_id"],
            chat_id=photo_row["chat_id"],
            author_id=photo_row["author_id"],
            author_name=photo_row["author_name"],
            anonymous=anonymous,
        )

        # Удаляем вопрос об анонимности
        await query.message.delete()

    # ------------------------------------------------------------------
    # Голосование за фото
    # ------------------------------------------------------------------
    elif data.startswith("rate_"):
        # Формат: rate_{photo_id}_{score}
        # photo_id может содержать символы, поэтому разбиваем с конца
        parts = data.rsplit("_", 1)         # ["rate_{photo_id}", "score"]
        score = int(parts[1])
        photo_id = parts[0][len("rate_"):]  # убираем префикс "rate_"

        voter_id = query.from_user.id
        avg, votes = add_vote(photo_id, voter_id, score)

        photo_row = get_photo(photo_id)
        if not photo_row:
            await query.answer("❌ Фото не найдено.", show_alert=True)
            return

        if photo_row["anonymous"]:
            caption = "🖼 Анонимное фото"
        else:
            caption = f"🖼 Фото от {photo_row['author_name']}"

        caption += f"\n\n⭐ Средняя оценка: {avg} ({votes} голос(ов))"

        # Обновляем подпись под фото
        await query.edit_message_caption(
            caption=caption,
            reply_markup=_rating_keyboard(photo_id),
        )
