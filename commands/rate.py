# ==============================================================================
# commands/rate.py — /rate: оценка фото (только в личке → постит в группу)
# ==============================================================================

import hashlib
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import save_photo, add_vote, get_photo, get_photo_by_key, close_photo, track_bot_message
import config
from config import VOTE_DURATION, WEBAPP_URL
from chat_config import get_setting
from chat_config import get_main_chat_id

logger = logging.getLogger(__name__)
PHOTOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "photos"))

# Состояние флоу /rate в личке
_COMMENT_WAITING: dict[int, str] = {}        # user_id → key (ждём текст подписи)
_PHOTO_CAPTIONS: dict[str, str] = {}         # key → текст подписи (для активных голосований)
_RATE_PM_MSGS: dict[int, list[int]] = {}     # user_id → [message_ids] для удаления
_RATE_WAITING: set[int] = set()              # user_id → ожидает отправки фото/видео после /rate
_PENDING_PHOTOS: dict[str, dict] = {}       # key → данные фото (до подтверждения публикации)


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
    pm_chat_id = update.effective_chat.id
    _RATE_PM_MSGS[user_id] = []
    _RATE_WAITING.add(user_id)  # ждём фото/видео

    # Таймаут 5 минут — если не отправит медиа, уведомляем и чистим
    async def _rate_timeout(ctx):
        _RATE_WAITING.discard(user_id)
        tracked = list(_RATE_PM_MSGS.pop(user_id, []))
        try:
            timeout_msg = await ctx.bot.send_message(
                chat_id=pm_chat_id,
                text="⏰ Время на отправку истекло. Используй /rate снова.",
            )
            tracked.append(timeout_msg.message_id)
        except Exception:
            pass
        # Удаляем все PM-сообщения через 10 секунд
        if tracked:
            async def _del_all(c):
                for mid in tracked:
                    try:
                        await c.bot.delete_message(pm_chat_id, mid)
                    except Exception:
                        pass
            ctx.job_queue.run_once(_del_all, 10)

    context.job_queue.run_once(_rate_timeout, 300, name=f"rate_timeout_{user_id}")

    try:
        await update.message.delete()
    except Exception:
        pass

    msg = await context.bot.send_message(
        chat_id=pm_chat_id,
        text=(
            "📸🎥 Отправь мне фото или видео, которое хочешь выставить на оценку группы.\n"
            f"Голосование будет идти {get_setting('vote_duration')} минут, затем покажу итоговый счёт."
        ),
    )
    _RATE_PM_MSGS[user_id].append(msg.message_id)


async def _process_media(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_id: str, media_type: str) -> None:
    """Общая логика обработки медиа (фото или видео)."""
    key = _short_key(photo_id)
    author = update.effective_user
    author_name = f"@{author.username}" if author.username else author.first_name

    # Сохраняем в память, НЕ в БД — в БД попадёт только после подтверждения публикации
    _PENDING_PHOTOS[key] = {
        "photo_id": photo_id,
        "author_id": author.id,
        "author_name": author_name,
        "media_type": media_type,
    }

    # Таймаут 10 минут — если не подтвердит, чистим из памяти
    uid_for_cleanup = author.id
    async def _pending_timeout(ctx):
        _PENDING_PHOTOS.pop(key, None)
        _PHOTO_CAPTIONS.pop(key, None)
        _RATE_PM_MSGS.pop(uid_for_cleanup, None)
        # Если пользователь нажал «добавить подпись» но так и не написал
        if _COMMENT_WAITING.get(uid_for_cleanup) == key:
            _COMMENT_WAITING.pop(uid_for_cleanup, None)
    context.job_queue.run_once(_pending_timeout, 600, name=f"pending_photo_{key}")

    user_id = author.id
    if user_id not in _RATE_PM_MSGS:
        _RATE_PM_MSGS[user_id] = []
    _RATE_PM_MSGS[user_id].append(update.message.message_id)

    msg = await update.message.reply_text(
        "💬 Хочешь добавить подпись к публикации?",
        reply_markup=_caption_keyboard(key),
    )
    _RATE_PM_MSGS[user_id].append(msg.message_id)


def _cancel_rate_timeout(context, user_id: int) -> None:
    """Отменяет таймаут ожидания фото/видео."""
    for job in context.job_queue.get_jobs_by_name(f"rate_timeout_{user_id}"):
        job.schedule_removal()


async def handle_rate_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает фото в личке — только если пользователь инициировал /rate."""
    user_id = update.effective_user.id
    if user_id not in _RATE_WAITING:
        return  # игнорируем фото без /rate
    _RATE_WAITING.discard(user_id)
    _cancel_rate_timeout(context, user_id)
    photo = update.message.photo[-1]
    await _process_media(update, context, photo.file_id, "photo")


async def handle_rate_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает видео в личке — только если пользователь инициировал /rate."""
    user_id = update.effective_user.id
    if user_id not in _RATE_WAITING:
        return  # игнорируем видео без /rate
    _RATE_WAITING.discard(user_id)
    _cancel_rate_timeout(context, user_id)
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

    text = (update.message.text or "").strip()

    if not text:
        await update.message.reply_text("❌ Пустая подпись. Напиши что-нибудь:")
        return True

    key = _COMMENT_WAITING.pop(user_id)

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
        _PHOTO_CAPTIONS.pop(key, None)
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

        photo_row = _PENDING_PHOTOS.pop(key, None)
        if not photo_row:
            await query.answer()
            await query.edit_message_text("❌ Фото не найдено. Отправь фото заново.")
            return

        photo_id = photo_row["photo_id"]

        # Используем основную группу; если не задана — fallback на config.CHAT_ID
        target_chat_id = get_main_chat_id() or config.CHAT_ID
        if not target_chat_id:
            await query.answer()
            await query.edit_message_text(
                "❌ Основная группа не настроена.\n"
                "Владелец должен назначить её через /settings → Чаты бота."
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
        vote_min = get_setting("vote_duration")
        group_caption += f"\n\n⭐ Голосуй от 1 до 10! Голосование идёт {vote_min} минут.\n📊 Сейчас: нет голосов"

        try:
            if is_video:
                sent = await context.bot.send_video(
                    chat_id=target_chat_id,
                    video=photo_id,
                    caption=group_caption,
                    reply_markup=_rating_keyboard(key),
                )
            else:
                sent = await context.bot.send_photo(
                    chat_id=target_chat_id,
                    photo=photo_id,
                    caption=group_caption,
                    reply_markup=_rating_keyboard(key),
                )
        except Exception as e:
            import html as _html
            logger.error("send_%s failed: chat_id=%s error=%s", media_type, target_chat_id, e)
            # Удаляем PM-сообщения даже при ошибке отправки
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
            await query.answer()
            await query.edit_message_text(
                f"❌ Не удалось отправить {media_word} в группу.\n"
                f"CHAT_ID: <code>{target_chat_id}</code>\n"
                f"Ошибка: <code>{_html.escape(str(e))}</code>\n\n"
                f"Проверь: бот добавлен в группу? Напиши /debug в группе.",
                parse_mode="HTML",
            )
            return

        # Отслеживаем сообщение бота в группе для /delmsg
        track_bot_message(target_chat_id, sent.message_id, group_caption[:80])

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
        await query.answer()
        await query.edit_message_text(
            f"✅ {media_word.capitalize()} отправлено в группу!\n"
            f"Голосование закроется через {get_setting('vote_duration')} минут — итог появится там."
        )

        save_photo(
            photo_id=photo_id,
            message_id=sent.message_id,
            chat_id=target_chat_id,
            author_id=photo_row["author_id"],
            author_name=photo_row["author_name"],
            anonymous=anonymous,
            key=key,
            media_type=media_type,
        )

        vote_duration = get_setting("vote_duration") * 60  # минуты → секунды
        context.job_queue.run_once(
            _close_rate_voting,
            vote_duration,
            data={"photo_id": photo_id, "chat_id": target_chat_id, "message_id": sent.message_id, "key": key},
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
            await query.answer("❌ Некорректные данные.")
            return
        key = parts[0][5:]  # убираем "rate_"

        photo_row = get_photo_by_key(key)
        if not photo_row:
            await query.answer("❌ Фото не найдено.")
            return

        photo_id = photo_row["photo_id"]

        if photo_row["closed"]:
            await query.answer("⏰ Голосование уже завершено!")
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
        if voter_id == photo_row["author_id"]:
            mt = photo_row["media_type"] if photo_row["media_type"] else "photo"
            mw = "видео" if mt == "video" else "фото"
            await query.answer(f"🚫 Нельзя голосовать за своё {mw}!")
            return

        avg, votes = add_vote(photo_id, voter_id, score)

        caption = _build_active_caption(photo_row, key)
        caption += (
            f"\n\n⭐ Голосуй от 1 до 10! Голосование идёт {get_setting('vote_duration')} минут.\n"
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
