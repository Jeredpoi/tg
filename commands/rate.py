# ==============================================================================
# commands/rate.py — Система оценки фото
# ==============================================================================

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
        InlineKeyboardButton("❌ Нет",        callback_data=f"anon_{photo_id}_no"),
    ]])


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /rate.
    Пользователь должен ответить на фото командой /rate.
    Бот спрашивает: скрыть автора?
    """
    message = update.message

    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text(
            "📸 Ответь командой /rate на фотографию, которую хочешь оценить."
        )
        return

    replied = message.reply_to_message
    photo = replied.photo[-1]   # наибольшее разрешение
    photo_id = photo.file_id

    author = replied.from_user
    author_name = f"@{author.username}" if author.username else author.first_name

    save_photo(
        photo_id=photo_id,
        message_id=replied.message_id,
        chat_id=message.chat_id,
        author_id=author.id,
        author_name=author_name,
        anonymous=False,
    )

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
    # Формат: anon_{photo_id}_yes  или  anon_{photo_id}_no
    # ВАЖНО: photo_id (Telegram file_id) может содержать символ '_',
    # поэтому разбираем через endswith, а не split.
    # ------------------------------------------------------------------
    if data.startswith("anon_"):
        if data.endswith("_yes"):
            photo_id = data[5:-4]   # убираем "anon_" и "_yes"
            anonymous = True
        else:
            photo_id = data[5:-3]   # убираем "anon_" и "_no"
            anonymous = False

        photo_row = get_photo(photo_id)
        if not photo_row:
            await query.edit_message_text("❌ Фото не найдено в базе.")
            return

        caption = "🖼 Анонимное фото" if anonymous else f"🖼 Фото от {photo_row['author_name']}"

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo_id,
            caption=f"{caption}\n\n⭐ Средняя оценка: нет голосов",
            reply_markup=_rating_keyboard(photo_id),
        )

        save_photo(
            photo_id=photo_id,
            message_id=photo_row["message_id"],
            chat_id=photo_row["chat_id"],
            author_id=photo_row["author_id"],
            author_name=photo_row["author_name"],
            anonymous=anonymous,
        )

        await query.message.delete()

    # ------------------------------------------------------------------
    # Голосование за фото
    # Формат: rate_{photo_id}_{score}  (score — число 1–10, без '_')
    # Разбиваем rsplit с правого конца: безопасно, т.к. score без '_'.
    # ------------------------------------------------------------------
    elif data.startswith("rate_"):
        parts = data.rsplit("_", 1)         # ["rate_{photo_id}", "{score}"]
        score = int(parts[1])
        photo_id = parts[0][5:]             # убираем префикс "rate_"

        voter_id = query.from_user.id
        avg, votes = add_vote(photo_id, voter_id, score)

        photo_row = get_photo(photo_id)
        if not photo_row:
            await query.answer("❌ Фото не найдено.", show_alert=True)
            return

        caption = (
            "🖼 Анонимное фото"
            if photo_row["anonymous"]
            else f"🖼 Фото от {photo_row['author_name']}"
        )
        caption += f"\n\n⭐ Средняя оценка: {avg} ({votes} голос(ов))"

        await query.edit_message_caption(
            caption=caption,
            reply_markup=_rating_keyboard(photo_id),
        )
