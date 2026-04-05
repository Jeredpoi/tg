# ==============================================================================
# commands/message_tracker.py — обработка входящих сообщений
# Extracted from bot.py to keep the main file manageable.
# ==============================================================================

import datetime
import logging
import os
import random
import time

from swear_detector import (
    _count_swears,
    FORWARD_RESPONSES, NAME_RESPONSES, SWEAR_RESPONSES, FLOOD_RESPONSES,
)
from config import SWEAR_COOLDOWN, SWEAR_RESPONSE_DELAY
from database import (
    track_message, track_daily_swear,
    get_user_stats, update_streak,
    get_chat_total_msg_count, get_days_since_last_activity,
    track_bot_message,
    get_user_today_msg_count, check_and_update_daily_record,
)
from chat_config import (
    get_setting, get_custom_swear_responses, get_custom_swear_triggers,
    is_monitor_chat,
)
from commands.achievements import (
    check_message_achievements, check_streak_achievements,
    check_time_achievements, check_single_message_achievements,
    check_activity_achievements, check_secret_text_achievements,
)

logger = logging.getLogger(__name__)

_MSK = datetime.timezone(datetime.timedelta(hours=3))

# ── In-memory state ───────────────────────────────────────────────────────────
# chat_id → (user_id, text, timestamp) — последнее сообщение другого юзера
_last_chat_msg:    dict[int,   tuple[int, str, float]] = {}
# (user_id, chat_id) → text
_user_last_msg:    dict[tuple, str]                   = {}
# (user_id, chat_id) → list[timestamp] — для speedrun (10 сек окно)
_user_recent_times: dict[tuple, list]                 = {}
# (user_id, chat_id) → list[str] — история до 50, НЕ чистим каждый час (deja_vu)
_user_msg_history:  dict[tuple, list]                 = {}

# Cooldown-словари для реакций
_forward_last:        dict[int, float] = {}
_mention_last:        dict[int, float] = {}
_swear_last_response: dict[int, float] = {}

_SWEAR_COOLDOWN   = SWEAR_COOLDOWN
_FORWARD_COOLDOWN = 30
_MENTION_COOLDOWN = 20
_FORWARD_CHANCE   = 0.4
_MENTION_CHANCE   = 0.7

# ── Антифлуд ─────────────────────────────────────────────────────────────────
# chat_id → (user_id, count) — подряд идущие сообщения от одного юзера
_flood_counter: dict[int, tuple[int, int]] = {}
# chat_id → timestamp последней реакции на флуд
_flood_last:    dict[int, float]           = {}
_FLOOD_THRESHOLD = 5
_FLOOD_COOLDOWN  = 600  # 10 минут

# ── Дневной рекорд — анонсируем только раз в день ────────────────────────────
# (user_id, chat_id) → date string "YYYY-MM-DD" последнего анонса
_record_announced: dict[tuple, str] = {}

# ── Аватары ───────────────────────────────────────────────────────────────────
_avatar_cache_set: set[int] = set()
_AVATARS_DIR = os.path.join(os.path.dirname(__file__), "..", "photos", "avatars")
_AVATAR_TTL  = 24 * 3600


def clear_avatar_cache() -> None:
    """Сбросить кэш аватаров (раз в 24 ч)."""
    _avatar_cache_set.clear()
    logger.debug("_avatar_cache_set: сброшен")


def cleanup_state() -> None:
    """
    Ежечасовая очистка краткосрочного in-memory состояния.
    _user_msg_history НЕ чистится (нужна для deja_vu).
    """
    _user_recent_times.clear()
    _last_chat_msg.clear()
    _flood_counter.clear()
    cutoff = time.time() - 7200
    for d in (_forward_last, _mention_last, _swear_last_response, _flood_last):
        stale = [k for k, v in d.items() if v < cutoff]
        for k in stale:
            d.pop(k, None)


# ── Фоновые задачи ────────────────────────────────────────────────────────────

async def _cache_avatar(context, user_id: int) -> None:
    """Скачать и сохранить аватар пользователя на диск."""
    os.makedirs(_AVATARS_DIR, exist_ok=True)
    cache_path = os.path.join(_AVATARS_DIR, f"{user_id}.jpg")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) < _AVATAR_TTL:
            return
    try:
        photos = await context.bot.get_user_profile_photos(user_id=user_id, limit=1)
        if not photos.total_count:
            return
        file_obj = await context.bot.get_file(photos.photos[0][-1].file_id)
        await file_obj.download_to_drive(cache_path)
    except Exception:
        pass


async def _send_swear_response(context) -> None:
    """Job: отправляет ответ на мат после дебаунс-паузы."""
    d = context.job.data
    chat_id = d["chat_id"]

    last = _swear_last_response.get(chat_id, 0)
    if time.time() - last < _SWEAR_COOLDOWN:
        return

    try:
        custom_response = d.get("custom_response")
        if custom_response:
            template = custom_response
        else:
            all_responses = SWEAR_RESPONSES + get_custom_swear_responses()
            template = random.choice(all_responses)
        try:
            text = template.format(name=d["name"])
        except (KeyError, IndexError):
            text = template.replace("{name}", d["name"])
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=d["message_id"],
        )
        _swear_last_response[chat_id] = time.time()
        track_bot_message(chat_id, msg.message_id, msg.text)
    except Exception as e:
        logger.warning("_send_swear_response: chat=%s err=%s", chat_id, e)


# ── Главный обработчик ────────────────────────────────────────────────────────

async def track_message_handler(update, context) -> None:
    """
    Обрабатывает каждое входящее сообщение:
    считает статистику, проверяет ачивки, реагирует на маты/форварды/упоминания.
    """
    if not update.message:
        return
    user = update.effective_user
    if not user or user.is_bot:
        return

    # Монитор-группа — не трекаем активность
    if update.effective_chat and is_monitor_chat(update.effective_chat.id):
        return

    # Кэшируем аватар один раз за сессию
    if user.id not in _avatar_cache_set:
        _avatar_cache_set.add(user.id)
        uid = user.id
        async def _do_cache_avatar(ctx):
            await _cache_avatar(ctx, uid)
        context.job_queue.run_once(_do_cache_avatar, 0, name=f"avatar_{uid}")

    chat_id   = update.effective_chat.id
    chat_type = update.effective_chat.type
    is_group  = chat_type in ("group", "supergroup")
    text      = update.message.text or update.message.caption or ""
    swear_count = _count_swears(text)

    # ── Capture in-memory state ──────────────────────────────────────────────
    _now_ts  = time.time()
    _uid_cid = (user.id, chat_id)

    _prev_chat_entry = _last_chat_msg.get(chat_id)
    _prev_chat_text  = (
        _prev_chat_entry[1]
        if (_prev_chat_entry and _prev_chat_entry[0] != user.id)
        else None
    )

    _reply_delta: float | None = None
    if update.message.reply_to_message:
        orig_ts = update.message.reply_to_message.date
        curr_ts = update.message.date
        if orig_ts and curr_ts:
            _reply_delta = (curr_ts - orig_ts).total_seconds()

    _hist      = _user_msg_history.setdefault(_uid_cid, [])
    _snap_hist = list(_hist)

    _u_times = _user_recent_times.setdefault(_uid_cid, [])
    _u_times.append(_now_ts)
    _u_times[:] = [t for t in _u_times if _now_ts - t <= 10]
    _recent_msg_count = len(_u_times)

    # Update state for next messages
    if text:
        _user_last_msg[_uid_cid] = text
        _last_chat_msg[chat_id]  = (user.id, text, _now_ts)
        _hist.append(text)
        if len(_hist) > 50:
            _hist.pop(0)

    # ── DB tracking ──────────────────────────────────────────────────────────
    track_message(user.id, user.username, user.first_name, swear_count, chat_id)

    if swear_count and is_group:
        track_daily_swear(
            chat_id, user.id,
            user.first_name or user.username or "Аноним",
            swear_count,
        )

    # ── Стрики и ачивки ──────────────────────────────────────────────────────
    if is_group:
        try:
            _user_name = user.first_name or user.username or "Участник"
            _uid, _cid = user.id, chat_id

            _days_absent = get_days_since_last_activity(_uid, _cid)
            streak, is_new_day = update_streak(_uid, _cid)

            if is_new_day:
                _streak = streak
                _absent = _days_absent
                async def _run_streak_check(ctx):
                    await check_streak_achievements(ctx.bot, _cid, _uid, _user_name, _streak)
                    await check_activity_achievements(ctx.bot, _cid, _uid, _user_name,
                                                      daily_count=0, days_since_last=_absent)
                context.job_queue.run_once(_run_streak_check, 1)

            stats = get_user_stats(_uid, _cid)
            _mc, _sc      = stats["msg_count"], stats["swear_count"]
            _swear_in_msg = swear_count
            _total_msgs   = get_chat_total_msg_count(_cid)
            _msg_text     = text
            _silence_hrs  = _days_absent * 24.0
            _pct          = _prev_chat_text
            _hist_snap    = _snap_hist
            _rmc          = _recent_msg_count
            _rd           = _reply_delta

            async def _run_msg_check(ctx):
                await check_message_achievements(ctx.bot, _cid, _uid, _user_name, _mc, _sc)
                await check_single_message_achievements(ctx.bot, _cid, _uid, _user_name,
                                                        _swear_in_msg, _total_msgs)
                await check_secret_text_achievements(
                    ctx.bot, _cid, _uid, _user_name,
                    text=_msg_text,
                    reply_delta_secs=_rd,
                    prev_chat_text=_pct,
                    user_msg_history=_hist_snap,
                    user_recent_count=_rmc,
                    silence_hours=_silence_hrs,
                )
            context.job_queue.run_once(_run_msg_check, 1)

            _now_dt = datetime.datetime.now(_MSK)
            _dt = _now_dt
            async def _run_time_check(ctx):
                await check_time_achievements(ctx.bot, _cid, _uid, _user_name, _dt)
            context.job_queue.run_once(_run_time_check, 2)

        except Exception as e:
            logger.warning("streak/achievement check failed: %s", e)

    # ── Реакция на пересланные сообщения ─────────────────────────────────────
    if is_group and update.message.forward_origin is not None:
        now = time.time()
        if now - _forward_last.get(chat_id, 0) > _FORWARD_COOLDOWN:
            if random.random() < _FORWARD_CHANCE:
                name = user.first_name or user.username or "кто-то"
                resp = random.choice(FORWARD_RESPONSES).format(name=name)
                try:
                    await update.message.reply_text(resp)
                    _forward_last[chat_id] = now
                except Exception:
                    pass

    # ── Реакция на упоминание имени бота ─────────────────────────────────────
    if is_group and text:
        bot_name     = (context.bot.first_name or "").lower()
        bot_username = (context.bot.username or "").lower()
        text_lower   = text.lower()
        name_mentioned = (
            (bot_name and bot_name in text_lower) or
            (bot_username and f"@{bot_username}" in text_lower)
        )
        if name_mentioned and not text.startswith("/"):
            now = time.time()
            if now - _mention_last.get(chat_id, 0) > _MENTION_COOLDOWN:
                if random.random() < _MENTION_CHANCE:
                    try:
                        await update.message.reply_text(random.choice(NAME_RESPONSES))
                        _mention_last[chat_id] = now
                    except Exception:
                        pass

    # ── Маты: кастомные триггеры ─────────────────────────────────────────────
    custom_triggers = get_custom_swear_triggers() if get_setting("swear_detect") else []
    matched_trigger = None
    if custom_triggers and text:
        text_lower = text.lower()
        for trigger in custom_triggers:
            if trigger["word"] in text_lower:
                matched_trigger = trigger
                break

    if matched_trigger and is_group:
        name = user.first_name or user.username or "дружок"
        for job in context.job_queue.get_jobs_by_name(f"swear_{chat_id}"):
            job.schedule_removal()
        if random.random() < get_setting("swear_response_chance"):
            context.job_queue.run_once(
                _send_swear_response,
                SWEAR_RESPONSE_DELAY,
                data={
                    "chat_id":         chat_id,
                    "name":            name,
                    "message_id":      update.message.message_id,
                    "custom_response": matched_trigger.get("response"),
                },
                name=f"swear_{chat_id}",
            )

    elif swear_count and chat_type != "private" and get_setting("swear_detect"):
        name = user.first_name or user.username or "дружок"
        for job in context.job_queue.get_jobs_by_name(f"swear_{chat_id}"):
            job.schedule_removal()
        if random.random() < get_setting("swear_response_chance"):
            context.job_queue.run_once(
                _send_swear_response,
                SWEAR_RESPONSE_DELAY,
                data={
                    "chat_id":    chat_id,
                    "name":       name,
                    "message_id": update.message.message_id,
                },
                name=f"swear_{chat_id}",
            )

    # ── Дневной рекорд ───────────────────────────────────────────────────────
    if is_group:
        try:
            _name = user.first_name or user.username or "Участник"
            today_count = get_user_today_msg_count(user.id, chat_id)
            if today_count >= 10:
                _rec_key  = (user.id, chat_id)
                _today_dt = datetime.datetime.now(_MSK).strftime("%Y-%m-%d")
                # Анонсируем рекорд только один раз в день
                if _record_announced.get(_rec_key) != _today_dt:
                    is_record = check_and_update_daily_record(user.id, chat_id, today_count)
                    if is_record:
                        _record_announced[_rec_key] = _today_dt
                        await update.message.reply_text(
                            f"🏆 {_name} побил личный рекорд — <b>{today_count}</b> сообщений за сегодня!",
                            parse_mode="HTML",
                        )
        except Exception as e:
            logger.debug("daily_record check failed: %s", e)

    # ── Антифлуд-реакция ─────────────────────────────────────────────────────
    if is_group and get_setting("flood_react"):
        try:
            prev = _flood_counter.get(chat_id)
            if prev and prev[0] == user.id:
                flood_count = prev[1] + 1
            else:
                flood_count = 1
            _flood_counter[chat_id] = (user.id, flood_count)

            if flood_count >= _FLOOD_THRESHOLD:
                now = time.time()
                if now - _flood_last.get(chat_id, 0) > _FLOOD_COOLDOWN:
                    _name = user.first_name or user.username or "кто-то"
                    resp = random.choice(FLOOD_RESPONSES).format(name=_name)
                    await update.message.reply_text(resp)
                    _flood_last[chat_id] = now
                    _flood_counter[chat_id] = (user.id, 0)
        except Exception as e:
            logger.debug("flood_react failed: %s", e)
