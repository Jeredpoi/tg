# ==============================================================================
# commands/rate.py — /rate: оценка фото (только в личке → постит в группу)
# ==============================================================================

import hashlib
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from database import save_photo, add_vote, get_photo, get_photo_by_key, close_photo
import config
from config import VOTE_DURATION, WEBAPP_URL

logger = logging.getLogger(__name__)
PHOTOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "photos"))


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
            "Напиши мне в личку — там отправь фото или видео для оценки группой."
        )
        return

    await update.message.reply_text(
        "📸🎥 Отправь мне фото или видео, которое хочешь выставить на оценку группы.\n"
        "Голосование будет идти 30 минут, затем покажу итоговый счёт."
    )


async def handle_rate_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает фото в личке и предлагает выставить на оценку группы."""
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
        media_type="photo",
    )

    await update.message.reply_text(
        "🤔 Скрыть тебя как автора в группе?",
        reply_markup=_anon_keyboard(key),
    )


async def handle_rate_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает видео в личке и предлагает выставить на оценку группы."""
    video = update.message.video
    video_id = video.file_id
    key = _short_key(video_id)
    author = update.effective_user
    author_name = f"@{author.username}" if author.username else author.first_name

    save_photo(
        photo_id=video_id,
        message_id=update.message.message_id,
        chat_id=config.CHAT_ID,
        author_id=author.id,
        author_name=author_name,
        anonymous=False,
        key=key,
        media_type="video",
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

    mt = photo_row["media_type"] if photo_row["media_type"] else "photo"
    me = "🎥" if mt == "video" else "🖼"
    mw = "видео" if mt == "video" else "фото"
    caption = f"{me} Анонимное {mw}" if photo_row["anonymous"] else f"{me} {mw.capitalize()} от {photo_row['author_name']}"
    caption += (
        f"\n\n🏁 Голосование завершено!\n"
        f"⭐ Средняя оценка: {avg} ({votes} голос(ов))"
    )

    try:
        gallery_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("🖼 Галерея", web_app=WebAppInfo(url=WEBAPP_URL))
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

        media_type = photo_row["media_type"] if photo_row["media_type"] else "photo"
        is_video = media_type == "video"
        media_emoji = "🎥" if is_video else "🖼"
        media_word = "видео" if is_video else "фото"

        caption = f"{media_emoji} Анонимное {media_word}" if anonymous else f"{media_emoji} {media_word.capitalize()} от {photo_row['author_name']}"
        caption += "\n\n⭐ Голосуй от 1 до 10! Голосование идёт 30 минут.\n📊 Сейчас: нет голосов"

        try:
            if is_video:
                sent = await context.bot.send_video(
                    chat_id=config.CHAT_ID,
                    video=photo_id,
                    caption=caption,
                    reply_markup=_rating_keyboard(key),
                )
            else:
                sent = await context.bot.send_photo(
                    chat_id=config.CHAT_ID,
                    photo=photo_id,
                    caption=caption,
                    reply_markup=_rating_keyboard(key),
                )
        except Exception as e:
            logger.error("send_%s failed: chat_id=%s error=%s", media_type, config.CHAT_ID, e)
            await query.edit_message_text(
                f"❌ Не удалось отправить {media_word} в группу.\n"
                f"CHAT_ID: <code>{config.CHAT_ID}</code>\n"
                f"Ошибка: <code>{e}</code>\n\n"
                f"Проверь: бот добавлен в группу? Напиши /debug в группе.",
                parse_mode="HTML",
            )
            return

        # Сохраняем файл на диск — чтобы вебсервер мог отдавать его без Telegram API
        try:
            os.makedirs(PHOTOS_DIR, exist_ok=True)
            ext = "mp4" if is_video else "jpg"
            disk_path = os.path.join(PHOTOS_DIR, f"{key}.{ext}")
            if not os.path.exists(disk_path):
                tg_file = await context.bot.get_file(photo_id)
                await tg_file.download_to_drive(disk_path)
                logger.info("Файл сохранён на диск: %s", disk_path)
        except Exception as _e:
            logger.warning("Не удалось сохранить файл на диск: %s", _e)

        # Сообщаем пользователю сразу — до любых операций с БД/job_queue
        await query.edit_message_text(
            f"✅ {media_word.capitalize()} отправлено в группу!\n"
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
            media_type=media_type,
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
            # Убираем кнопки голосования, оставляем только галерею
            try:
                total = photo_row["total_score"]
                votes = photo_row["vote_count"]
                avg = round(total / votes, 2) if votes > 0 else 0
                mt = photo_row["media_type"] if photo_row["media_type"] else "photo"
                me = "🎥" if mt == "video" else "🖼"
                mw = "видео" if mt == "video" else "фото"
                caption = f"{me} Анонимное {mw}" if photo_row["anonymous"] else f"{me} {mw.capitalize()} от {photo_row['author_name']}"
                caption += f"\n\n🏁 Голосование завершено!\n⭐ Средняя оценка: {avg} ({votes} голос(ов))"
                gallery_btn = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🖼 Галерея", web_app=WebAppInfo(url=WEBAPP_URL))
                ]])
                await query.edit_message_caption(caption=caption, reply_markup=gallery_btn)
            except Exception:
                pass
            return

        voter_id = query.from_user.id
        # Блокируем автора только в публичном режиме
        if voter_id == photo_row["author_id"] and not photo_row["anonymous"]:
            mt = photo_row["media_type"] if photo_row["media_type"] else "photo"
            mw = "видео" if mt == "video" else "фото"
            await query.answer(f"🚫 Нельзя голосовать за своё {mw}!", show_alert=True)
            return

        avg, votes = add_vote(photo_id, voter_id, score)

        mt = photo_row["media_type"] if photo_row["media_type"] else "photo"
        me = "🎥" if mt == "video" else "🖼"
        mw = "видео" if mt == "video" else "фото"
        caption = f"{me} Анонимное {mw}" if photo_row["anonymous"] else f"{me} {mw.capitalize()} от {photo_row['author_name']}"
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
