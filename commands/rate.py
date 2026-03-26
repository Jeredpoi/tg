# ==============================================================================
# commands/rate.py — /rate: оценка фото (только в личке → постит в группу)
# ==============================================================================

import hashlib
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import save_photo, add_vote, get_photo, get_photo_by_key, close_photo
import config
from config import VOTE_DURATION, WEBAPP_URL

logger = logging.getLogger(__name__)
PHOTOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "photos"))

# Состояние флоу /rate в личке
_COMMENT_WAITING: dict[int, str] = {}        # user_id → key (ждём текст подписи)
_PHOTO_CAPTIONS: dict[str, str] = {}         # key → текст подписи (для активных голосований)
_RATE_PM_MSGS: dict[int, list[int]] = {}     # user_id → [message_ids] для удаления


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


def _caption_keyboard(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✏️ Добавить подпись", callback_data=f"comment_ask_{key}"),
        InlineKeyboardButton("➡️ Пропустить",       callback_data=f"comment_skip_{key}"),
    ]])


async def _delete_rate_pm(context) -> None:
    """Job: удаляет все промежуточные PM-сообщения флоу /rate."""
    data = context.job.data
    chat_id = data["chat_id"]
    for mid in data["msg_ids"]:
        try:
            await context.bot.delete_message(chat_id, mid)
        except Exception:
            pass


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "📸 Команда /rate работает только в личных сообщениях!\n"
            "Напиши мне в личку — там отправь фото или видео для оценки группой."
        )
        return

    user_id = update.effective_user.id
    _RATE_PM_MSGS[user_id] = []

    try:
        await update.message.delete()
    except Exception:
        pass

    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "📸🎥 Отправь мне фото или видео, которое хочешь выставить на оценку группы.\n"
            "Голосование будет идти 30 минут, затем покажу итоговый счёт."
        ),
    )
    _RATE_PM_MSGS[user_id].append(msg.message_id)


async def _process_media(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_id: str, media_type: str) -> None:
    """Общая логика обработки медиа (фото или видео)."""
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
        media_type=media_type,
    )

    user_id = author.id
    if user_id not in _RATE_PM_MSGS:
        _RATE_PM_MSGS[user_id] = []
    _RATE_PM_MSGS[user_id].append(update.message.message_id)

    msg = await update.message.reply_text(
        "💬 Хочешь добавить подпись к публикации?",
        reply_markup=_caption_keyboard(key),
    )
    _RATE_PM_MSGS[user_id].append(msg.message_id)


async def handle_rate_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает фото в личке и предлагает выставить на оценку группы."""
    photo = update.message.photo[-1]
    await _process_media(update, context, photo.file_id, "photo")


async def handle_rate_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает видео в личке и предлагает выставить на оценку группы."""
    video = update.message.video
    await _process_media(update, context, video.file_id, "video")


async def handle_rate_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Вызывается из bot.py когда пользователь печатает текст в личке.
    Возвращает True если текст был обработан как подпись к /rate.
    """
    if update.effective_chat.type != "private":
        return False

    user_id = update.effective_user.id
    if user_id not in _COMMENT_WAITING:
        return False

    key = _COMMENT_WAITING.pop(user_id)
    text = (update.message.text or "").strip()

    if not text:
        await update.message.reply_text("❌ Пустая подпись. Напиши что-нибудь или используй /rate заново.")
        return True

    _PHOTO_CAPTIONS[key] = text

    if user_id not in _RATE_PM_MSGS:
        _RATE_PM_MSGS[user_id] = []
    _RATE_PM_MSGS[user_id].append(update.message.message_id)

    msg = await update.message.reply_text(
        "🤔 Скрыть тебя как автора в группе?",
        reply_markup=_anon_keyboard(key),
    )
    _RATE_PM_MSGS[user_id].append(msg.message_id)
    return True


def _build_active_caption(photo_row: dict, key: str) -> str:
    """Строит подпись для активного голосования."""
    mt = photo_row["media_type"] if photo_row["media_type"] else "photo"
    me = "🎥" if mt == "video" else "🖼"
    mw = "видео" if mt == "video" else "фото"
    author_line = f"{me} Анонимное {mw}" if photo_row["anonymous"] else f"{me} {mw.capitalize()} от {photo_row['author_name']}"
    user_caption = _PHOTO_CAPTIONS.get(key, "")
    caption = author_line
    if user_caption:
        caption += f"\n{user_caption}"
    return caption


async def _close_rate_voting(context) -> None:
    """Job-функция: закрывает голосование через VOTE_DURATION секунд."""
    data = context.job.data
    photo_id = data["photo_id"]
    chat_id = data["chat_id"]
    message_id = data["message_id"]
    key = data.get("key", "")

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
    author_line = f"{me} Анонимное {mw}" if photo_row["anonymous"] else f"{me} {mw.capitalize()} от {photo_row['author_name']}"

    user_caption = _PHOTO_CAPTIONS.pop(key, "") if key else ""
    caption = author_line
    if user_caption:
        caption += f"\n{user_caption}"
    caption += (
        f"\n\n🏁 Голосование завершено!\n"
        f"⭐ Средняя оценка: {avg} ({votes} голос(ов))"
    )

    try:
        bot_username = context.bot.username
        gallery_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("🖼 Галерея", url=f"https://t.me/{bot_username}?start=gallery_{chat_id}")
        ]])
        await context.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=caption,
            reply_markup=gallery_btn,
        )
    except Exception as e:
        logger.error("Не удалось закрыть голосование chat=%s msg=%s: %s", chat_id, message_id, e)

    # Уведомление автору в личку
    author_id = photo_row.get("author_id")
    if author_id and not photo_row["anonymous"]:
        try:
            bot_username = context.bot.username
            avg_text = f"{avg}" if votes > 0 else "—"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Закрыть", callback_data="dismiss"),
                InlineKeyboardButton("🖼 Галерея", url=f"https://t.me/{bot_username}?start=gallery_{chat_id}"),
            ]])
            await context.bot.send_message(
                chat_id=author_id,
                text=(
                    "🏁 <b>Голосование по твоему медиа завершено!</b>\n\n"
                    f"⭐ Средняя оценка: <b>{avg_text}</b> из 10\n"
                    f"👥 Проголосовало: <b>{votes}</b> чел."
                ),
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            pass  # пользователь не начал диалог с ботом — молча игнорируем


async def rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data

    # ── Запрос подписи ────────────────────────────────────────────────────
    if data.startswith("comment_ask_"):
        key = data[12:]
        _COMMENT_WAITING[query.from_user.id] = key
        await query.answer()
        await query.edit_message_text("✏️ Отправь текст подписи:")
        return

    # ── Пропуск подписи ───────────────────────────────────────────────────
    if data.startswith("comment_skip_"):
        key = data[13:]
        await query.answer()
        await query.edit_message_text(
            "🤔 Скрыть тебя как автора в группе?",
            reply_markup=_anon_keyboard(key),
        )
        return

    # ── Выбор анонимности ─────────────────────────────────────────────────
    if data.startswith("anon_"):
        if data.endswith("_yes"):
            key = data[5:-4]
            anonymous = True
        else:
            key = data[5:-3]
            anonymous = False

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

        user_id = query.from_user.id
        user_caption = _PHOTO_CAPTIONS.get(key, "")

        author_line = f"{media_emoji} Анонимное {media_word}" if anonymous else f"{media_emoji} {media_word.capitalize()} от {photo_row['author_name']}"
        group_caption = author_line
        if user_caption:
            group_caption += f"\n{user_caption}"
        group_caption += "\n\n⭐ Голосуй от 1 до 10! Голосование идёт 30 минут.\n📊 Сейчас: нет голосов"

        try:
            if is_video:
                sent = await context.bot.send_video(
                    chat_id=config.CHAT_ID,
                    video=photo_id,
                    caption=group_caption,
                    reply_markup=_rating_keyboard(key),
                )
            else:
                sent = await context.bot.send_photo(
                    chat_id=config.CHAT_ID,
                    photo=photo_id,
                    caption=group_caption,
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

        # Сообщаем пользователю
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
            data={"photo_id": photo_id, "chat_id": config.CHAT_ID, "message_id": sent.message_id, "key": key},
        )

        # Планируем удаление всех PM-сообщений через 5 секунд
        pm_chat_id = query.message.chat_id
        current_msg_id = query.message.message_id
        tracked = list(_RATE_PM_MSGS.pop(user_id, []))
        if current_msg_id not in tracked:
            tracked.append(current_msg_id)
        context.job_queue.run_once(
            _delete_rate_pm,
            5,
            data={"chat_id": pm_chat_id, "msg_ids": tracked},
        )

    # ── Голосование ───────────────────────────────────────────────────────
    elif data.startswith("rate_"):
        parts = data.rsplit("_", 1)
        try:
            score = int(parts[1])
        except (IndexError, ValueError):
            await query.answer("❌ Некорректные данные.", show_alert=True)
            return
        key = parts[0][5:]  # убираем "rate_"

        photo_row = get_photo_by_key(key)
        if not photo_row:
            await query.answer("❌ Фото не найдено.", show_alert=True)
            return

        photo_id = photo_row["photo_id"]

        if photo_row["closed"]:
            await query.answer("⏰ Голосование уже завершено!", show_alert=True)
            try:
                total = photo_row["total_score"]
                votes = photo_row["vote_count"]
                avg = round(total / votes, 2) if votes > 0 else 0
                caption = _build_active_caption(photo_row, key)
                caption += f"\n\n🏁 Голосование завершено!\n⭐ Средняя оценка: {avg} ({votes} голос(ов))"
                bot_username = context.bot.username
                gallery_btn = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🖼 Галерея", url=f"https://t.me/{bot_username}?start=gallery_{query.message.chat_id}")
                ]])
                await query.edit_message_caption(caption=caption, reply_markup=gallery_btn)
            except Exception:
                pass
            return

        voter_id = query.from_user.id
        if voter_id == photo_row["author_id"] and not photo_row["anonymous"]:
            mt = photo_row["media_type"] if photo_row["media_type"] else "photo"
            mw = "видео" if mt == "video" else "фото"
            await query.answer(f"🚫 Нельзя голосовать за своё {mw}!", show_alert=True)
            return

        avg, votes = add_vote(photo_id, voter_id, score)

        caption = _build_active_caption(photo_row, key)
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
