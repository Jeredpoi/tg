# ==============================================================================
# bot.py — Главный файл бота
# ==============================================================================

import html as _html_mod
import logging
import logging.handlers
import math
import os
import re
import random
import time
import datetime
import urllib.parse
from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    filters,
)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from config import (BOT_TOKEN, PROXY_URL, WEBAPP_URL, OWNER_ID,
                    SWEAR_COOLDOWN, DEFAULT_CMD_COOLDOWN,
                    SWEAR_RESPONSE_DELAY, SWEAR_RESPONSE_CHANCE,
                    DATABASE_PATH)

from database import (init_db, get_daily_swear_report,
                       get_best_photo_since, get_and_delete_old_photos,
                       get_streak, track_bot_message, track_message,
                       save_pm_chat, get_pm_chat, get_users_at_streak_risk,
                       get_top_messages_since)
from commands.achievements import check_simple_achievements
from commands.message_tracker import (
    track_message_handler, cleanup_state, clear_avatar_cache,
    _send_swear_response,  # нужен для _handle_edited_message
)
from commands.achievements_cmd import achievements_command, achievements_callback, _send_achievements_menu

from commands.debug import debug_command
from commands.dice import dice_command
from commands.mge import mge_command
from commands.roast import roast_command
from commands.top import top_command, top_callback
from commands.rate import rate_command, rate_callback, handle_rate_photo, handle_rate_video, handle_rate_comment
from commands.help import help_command, ownerhelp_command, ownerhelp_pin_callback
from commands.stats import stats_command
from commands.anon import anon_command, handle_anon_cancel, handle_anon_message
from commands.clearmedia import clearmedia_command, clearmedia_callback
from commands.delmsg import delmsg_command, delmsg_callback
from commands.resend import resend_command, handle_resend_message, resend_cancel
from commands.settings import settings_command, settings_callback, handle_settings_input
from commands.exportstats import exportstats_command
from commands.maintenance import is_maintenance, maintenance_command
from commands.backup import backup_command
from commands.restart import restart_command, send_restart_done
from commands.dashboard import dashboard_callback, dashboard_update_job, DASHBOARD_UPDATE_INTERVAL, dashboard_command
from commands.clearstats import clearstats_command, clearstats_callback
from commands.botset import botset_command, handle_botset_photo, apply_identity
from commands.modtools import synccmds_command, giveach_command, revokeach_command, announce_command
from chat_config import (get_main_chat_id, add_setup_chat, is_setup_chat, get_setting,
                          is_command_enabled, get_custom_swear_responses, get_custom_swear_triggers,
                          sync_bot_commands, is_monitor_chat)


_LOG_FILE = os.path.join(os.path.dirname(__file__), "bot.log")

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
# Add rotating file handler (5 MB per file, keep 3 backups)
_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s — %(name)s — %(levelname)s — %(message)s"
))
logging.getLogger().addHandler(_file_handler)

logger = logging.getLogger(__name__)

from swear_detector import SWEAR_WORDS, _count_swears

# ==============================================================================
# Rate limiter — кулдаун команд на юзера
# ==============================================================================

# Кулдаун по умолчанию (секунды). Отдельные команды можно переопределить.
_DEFAULT_CMD_COOLDOWN = DEFAULT_CMD_COOLDOWN

# Переопределения для конкретных команд (0 = без лимита)
_CMD_COOLDOWNS: dict[str, int] = {
    "/help":  30,
    "/start": 0,
    "/debug": 0,
    "/anon":  30,
    "/rate":  300,  # фото в личке → чат, лимит 5 минут
}

# Словарь: (user_id, command) → timestamp последнего разрешённого вызова
_cmd_last_used: dict[tuple[int, str], float] = {}


async def _maintenance_guard(update, context):
    """Middleware (group=-3): блокирует все команды не-владельца в режиме обслуживания."""
    if not is_maintenance():
        return
    user = update.effective_user
    if user and user.id == OWNER_ID:
        return
    msg = update.message
    if msg:
        try:
            await msg.delete()
        except Exception:
            pass
        chat = update.effective_chat
        if chat and chat.type in ("group", "supergroup"):
            try:
                note = await context.bot.send_message(
                    chat_id=chat.id,
                    text="🔧 Бот на техническом обслуживании.",
                    disable_notification=True,
                )
                async def _del(ctx):
                    try:
                        await ctx.bot.delete_message(chat.id, note.message_id)
                    except Exception:
                        pass
                context.job_queue.run_once(_del, 5)
            except Exception:
                pass
    raise ApplicationHandlerStop


async def _rate_limit_guard(update, context):
    """Middleware (group=-1): при спаме команд уведомляет пользователя и останавливает обработку."""
    msg = update.message
    if not msg or not msg.text or not msg.text.startswith("/"):
        return

    user = update.effective_user
    if not user or user.is_bot:
        return

    # Нормализуем "/mge@botname" → "/mge"
    command = msg.text.split()[0].split("@")[0].lower()

    # Команда отключена владельцем — тихо удаляем
    if not is_command_enabled(command):
        if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
            try:
                await msg.delete()
            except Exception:
                pass
        raise ApplicationHandlerStop

    cooldown = _CMD_COOLDOWNS.get(command, get_setting("cmd_cooldown"))

    if cooldown == 0:
        return  # без лимита — пропускаем

    key = (user.id, command)
    now = time.time()
    last = _cmd_last_used.get(key, 0)

    if now - last < cooldown:
        remaining = math.ceil(cooldown - (now - last))
        chat = update.effective_chat
        if chat and chat.type in ("group", "supergroup"):
            # Удаляем команду при кулдауне только если autodel для неё включён
            _AUTODEL_KEYS = {
                "/dice":  "autodel_dice",
                "/mge":   "autodel_mge",
                "/roast": "autodel_roast",
            }
            _autodel_key = _AUTODEL_KEYS.get(command)
            if _autodel_key is None or get_setting(_autodel_key):
                try:
                    await msg.delete()
                except Exception:
                    pass
            try:
                note = await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"⏳ <b>{remaining} сек.</b> до следующего использования",
                    parse_mode="HTML",
                    disable_notification=True,
                )
                async def _del_cd(ctx):
                    try:
                        await ctx.bot.delete_message(chat.id, note.message_id)
                    except Exception:
                        pass
                context.job_queue.run_once(_del_cd, 2)
            except Exception:
                pass
        elif chat and chat.type == "private":
            try:
                await msg.delete()
            except Exception:
                pass
        raise ApplicationHandlerStop

    # Первый / разрешённый вызов — фиксируем время
    _cmd_last_used[key] = now

    # Считаем команду как сообщение пользователя в группе
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        track_message(user.id, user.username, user.first_name, 0, chat.id)


# ==============================================================================
# Setup guard — бот требует /start и права на удаление сообщений
# ==============================================================================

async def _setup_guard(update, context):
    """Middleware (group=-2): блокирует команды в не-инициализированных группах."""
    msg = update.message
    if not msg or not msg.text:
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return

    command = msg.text.split()[0].split("@")[0].lower()

    # Монитор-группа: разрешаем только /dashboard владельцу, всё остальное — удаляем тихо
    if is_monitor_chat(chat.id):
        if command != "/dashboard":
            try:
                await msg.delete()
            except Exception:
                pass
            raise ApplicationHandlerStop
        return

    # /start пропускаем всегда — через него происходит инициализация
    if command == "/start":
        return

    if not is_setup_chat(chat.id):
        await msg.reply_text("Сосунок, папочка пока не работает! Пропишите /start")
        raise ApplicationHandlerStop


async def _group_start_command(update, context):
    """Инициализация бота в группе через /start."""
    chat = update.effective_chat

    # Уже инициализирован — тихо удаляем команду
    if is_setup_chat(chat.id):
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    # Проверяем, есть ли у бота право удалять сообщения
    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    can_delete = getattr(bot_member, "can_delete_messages", False)

    if not can_delete:
        await update.message.reply_text(
            "Вы что тупые? Папочка сказал: дайте права на удаление сообщений! "
            "Выдайте — и снова пропишите /start"
        )
        return

    add_setup_chat(chat.id)
    await update.message.reply_text(
        "Молодец сынок, папочка начинает работать"
    )






def _save_chat_id_to_config(new_id: int) -> None:
    """Сохраняет CHAT_ID в .env файл."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    try:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
            new_content, count = re.subn(r"^CHAT_ID=.*$", f"CHAT_ID={new_id}", content, flags=re.MULTILINE)
            if count == 0:
                new_content = content.rstrip("\n") + f"\nCHAT_ID={new_id}\n"
        else:
            new_content = f"CHAT_ID={new_id}\n"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except OSError as e:
        logger.warning("_save_chat_id_to_config: не удалось записать .env — %s", e)


async def _on_bot_added(update, context):
    """Срабатывает когда бот добавлен в группу — сохраняет CHAT_ID."""
    event = update.my_chat_member
    new_status = event.new_chat_member.status
    chat = event.chat

    if new_status not in ("member", "administrator"):
        return
    if chat.type not in ("group", "supergroup"):
        return

    import config
    chat_id = chat.id

    # Монитор-группа — не перезаписываем CHAT_ID и не отправляем приветствие
    if is_monitor_chat(chat_id):
        logger.info("Бот добавлен в монитор-группу %r — CHAT_ID не меняем", chat.title)
        return

    config.CHAT_ID = chat_id
    _save_chat_id_to_config(chat_id)

    logger.info("Бот добавлен в группу %r, CHAT_ID обновлён на %s", chat.title, chat_id)

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Привет сосунки!\n\n"
                "Чтобы батя начал работать:\n"
                "1. Выдайте мне права на <b>удаление сообщений</b>\n"
                "2. Пропишите /start\n\n"
                "Пока не сделаете — ни одна команда работать не будет!"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def gallery_command(update, context):
    """Отправляет кнопку галереи через deep link — без личных данных в группе."""
    chat = update.effective_chat
    bot_username = context.bot.username
    # Ссылка ведёт в личку бота, где он выдаст персональный URL с uid/uname
    deep_url = f"https://t.me/{bot_username}?start=gallery_{chat.id}"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🖼 Открыть галерею", url=deep_url)
    ]])
    reply_to = update.message.reply_to_message
    if reply_to:
        msg = await reply_to.reply_text(
            "🖼 Нажми кнопку — бот пришлёт тебе персональную ссылку в личку:",
            reply_markup=kb,
        )
    else:
        msg = await update.message.reply_text(
            "🖼 Нажми кнопку — бот пришлёт тебе персональную ссылку в личку:",
            reply_markup=kb,
        )
    track_bot_message(chat.id, msg.message_id, "🖼 Галерея рейтингов")

    # Автоудаление через autodel_gallery секунд (команда + ответ бота)
    delay = get_setting("autodel_gallery")
    if delay:
        cmd_mid = update.message.message_id
        bot_mid = msg.message_id
        gal_chat_id = chat.id

        async def _del_gallery_msg(ctx):
            for mid in [cmd_mid, bot_mid]:
                try:
                    await ctx.bot.delete_message(gal_chat_id, mid)
                except Exception:
                    pass

        context.job_queue.run_once(_del_gallery_msg, delay)


async def _private_command_guard(update, context):
    """Отвечает на неизвестные команды в личке."""
    await update.message.reply_text(
        "❌ В личке доступны только:\n"
        "/rate — отправить фото на оценку группы\n"
        "/achievements — твои ачивки\n"
        "/help — список команд группы"
    )


_MIDNIGHT_MSGS = [
    "За сегодня вы насматерились <b>{total}</b> раз. Какие же вы мелочные 🤡",
    "Итог дня: <b>{total}</b> матерных слов. Культурный чат, ничего не скажешь 👏",
    "Папочка посчитал: <b>{total}</b> матов за день. Вы этим гордитесь? 😐",
    "Дневной рекорд по матам: <b>{total}</b>. Молодцы, сосунки 🏆",
    "Сегодня вы произнесли <b>{total}</b> матерных слов. Мама была бы в шоке 😳",
]

_MEDALS = ["🥇", "🥈", "🥉"]


_MIDNIGHT_ZERO_MSGS = [
    "За сегодня никто не матерился. Гордитесь собой, сосунки 🥲",
    "Чистый день — ни одного мата. Это было неожиданно 😶",
    "Сегодня культурные. Завтра всё равно сорвётесь 🫡",
]

async def _midnight_swear_report(context) -> None:
    """Job: в 00:00 МСК отправляет отчёт по матам за прошедший день."""
    if not get_setting("midnight_report"):
        return
    msk = datetime.timezone(datetime.timedelta(hours=3))
    yesterday = (datetime.datetime.now(msk).date() - datetime.timedelta(days=1)).isoformat()
    # Отправляем только в основную группу
    main_id = get_main_chat_id()
    if not main_id:
        logger.warning("midnight_swear_report: основная группа не назначена (/settings → Чаты бота)")
        return
    target_chats = {main_id}
    for chat_id in target_chats:
        try:
            total, rows = get_daily_swear_report(chat_id, yesterday)
            if total == 0:
                text = random.choice(_MIDNIGHT_ZERO_MSGS)
            else:
                header = random.choice(_MIDNIGHT_MSGS).format(total=total)
                lines = [f"🤬 {header}\n"]
                for i, (name, count) in enumerate(rows[:5]):
                    medal = _MEDALS[i] if i < 3 else f"{i + 1}."
                    lines.append(f"{medal} {_html_mod.escape(name or 'Аноним')} — {count} раз(а)")
                text = "\n".join(lines)
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            track_bot_message(chat_id, msg.message_id, text[:80])
        except Exception as e:
            logger.warning("midnight_swear_report chat=%s: %s", chat_id, e)


async def _private_start(update, context):
    """/start в личке — с поддержкой deep link для галереи (gallery_{chat_id})."""
    # Сохраняем PM chat_id для напоминаний о стрике
    user = update.effective_user
    if user:
        try:
            save_pm_chat(user.id, update.effective_chat.id)
        except Exception:
            pass

    if context.args and context.args[0].startswith("gallery_"):
        try:
            chat_id = int(context.args[0][8:])
        except ValueError:
            await help_command(update, context)
            return
        user = update.effective_user
        uname = urllib.parse.quote(user.username or user.first_name or str(user.id), safe='')
        url = f"{WEBAPP_URL}?uid={user.id}&uname={uname}&chat_id={chat_id}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Открыть галерею", url=url)]])
        bot_msg = await update.message.reply_text(
            "🖼 <b>Галерея рейтингов</b>\n\n"
            "Твоя персональная ссылка — имя будет отображаться в комментариях:",
            parse_mode="HTML",
            reply_markup=kb,
        )

        # Автоудаление обоих сообщений (задержка из настроек)
        delay = get_setting("autodel_gallery")
        if delay:
            pm_chat_id = update.effective_chat.id
            user_mid = update.message.message_id
            bot_mid = bot_msg.message_id

            async def _del_gallery(ctx):
                for mid in [user_mid, bot_mid]:
                    try:
                        await ctx.bot.delete_message(pm_chat_id, mid)
                    except Exception:
                        pass

            context.job_queue.run_once(_del_gallery, delay)
        return

    # Deep link: ?start=ach_{group_chat_id} → открыть меню ачивок для конкретной группы
    if context.args and context.args[0].startswith("ach_"):
        user = update.effective_user
        try:
            src_chat_id = int(context.args[0][4:])
        except ValueError:
            src_chat_id = get_main_chat_id() or update.effective_chat.id
        await _send_achievements_menu(
            context,
            pm_chat_id=update.effective_chat.id,
            user_id=user.id,
            src_chat_id=src_chat_id,
            user_name=user.first_name or user.username or "",
        )
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    # Deep link: ?start=anon_{group_chat_id} → сразу ожидаем анонимное сообщение
    if context.args and context.args[0].startswith("anon_"):
        user = update.effective_user
        try:
            src_chat_id = int(context.args[0][5:])
        except ValueError:
            src_chat_id = get_main_chat_id() or 0
        if src_chat_id:
            from commands.anon import _pending, ANON_TIMEOUT
            import time as _time
            _pending[user.id] = (src_chat_id, _time.time())
            async def _expire(ctx):
                _pending.pop(user.id, None)
            context.job_queue.run_once(_expire, ANON_TIMEOUT, name=f"anon_expire_{user.id}")
            await update.message.reply_text(
                "🎭 <b>Анонимное сообщение</b>\n\n"
                "Напиши сообщение — я отправлю его в группу без твоего имени.\n\n"
                "<i>У тебя есть 5 минут. /cancel для отмены.</i>",
                parse_mode="HTML",
            )
            return

    await help_command(update, context)


async def _weekly_best_photo(context) -> None:
    """Каждый понедельник в 00:00 МСК постит лучшее фото за неделю."""
    if not get_setting("weekly_best_photo"):
        return
    main_id = get_main_chat_id()
    if not main_id:
        logger.warning("weekly_best_photo: основная группа не назначена (/settings → Чаты бота)")
        return
    for chat_id in [main_id]:
        try:
            row = get_best_photo_since(days=7, chat_id=chat_id)
            if not row:
                continue
            votes = row["vote_count"]
            avg   = round(row["avg_score"], 1)
            author = "Аноним" if row["anonymous"] else _html_mod.escape(row["author_name"] or "Аноним")
            photo_id  = row["photo_id"]
            media_type = row["media_type"] or "photo"
            uname_q   = urllib.parse.quote("Скаут", safe="")
            gallery_url = f"{WEBAPP_URL}?chat_id={chat_id}&uname={uname_q}"
            caption = (
                f"🏆 <b>Лучшее фото недели!</b>\n\n"
                f"👤 Автор: {author}\n"
                f"⭐ Средняя оценка: {avg} ({votes} голос(ов))"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Галерея", url=gallery_url)]])
            if media_type == "video":
                msg = await context.bot.send_video(chat_id=chat_id, video=photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                msg = await context.bot.send_photo(chat_id=chat_id, photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            track_bot_message(chat_id, msg.message_id, caption[:80])
            logger.info("weekly_best_photo: отправлено в чат %s", chat_id)
        except Exception as e:
            logger.warning("weekly_best_photo chat=%s: %s", chat_id, e)


async def _cleanup_old_photos(context) -> None:
    """Ежедневно в 03:00 МСК удаляет фото/видео старше 30 дней с диска и из БД."""
    photos_dir = os.path.join(os.path.dirname(__file__), "photos")
    deleted_count = 0
    try:
        old = get_and_delete_old_photos(days=30)
        for key, media_type in old:
            primary_ext = "mp4" if media_type == "video" else "jpg"
            for ext in (primary_ext, "mp4" if primary_ext == "jpg" else "jpg"):
                fpath = os.path.join(photos_dir, f"{key}.{ext}")
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                        deleted_count += 1
                    except OSError as e:
                        logger.warning("cleanup_old_photos: не удалось удалить %s: %s", fpath, e)
        if deleted_count:
            logger.info("cleanup_old_photos: удалено %d файлов", deleted_count)
    except Exception as e:
        logger.error("cleanup_old_photos: %s", e)


async def _handle_edited_message(update, context):
    """При редактировании сообщения — отменяем pending swear job если маты убраны."""
    msg = update.edited_message
    if not msg:
        return
    text = msg.text or ""
    # Если в отредактированном тексте больше нет матов — отменяем запланированный ответ
    if _count_swears(text) == 0:
        chat_id = msg.chat_id
        for job in context.job_queue.get_jobs_by_name(f"swear_{chat_id}"):
            if job.data and job.data.get("message_id") == msg.message_id:
                job.schedule_removal()


def main():
    init_db()

    builder = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
    )
    if PROXY_URL:
        builder = builder.request(HTTPXRequest(proxy=PROXY_URL, read_timeout=15, write_timeout=15, connect_timeout=10))
        logger.info("Используется прокси: %s", PROXY_URL)
    else:
        builder = builder.request(HTTPXRequest(read_timeout=15, write_timeout=15, connect_timeout=10))
    app = builder.build()

    # Middleware: maintenance (group=-3) → setup (group=-2) → rate limit (group=-1)
    app.add_handler(
        MessageHandler(filters.COMMAND, _maintenance_guard),
        group=-3,
    )
    app.add_handler(
        MessageHandler(filters.COMMAND & filters.ChatType.GROUPS, _setup_guard),
        group=-2,
    )
    app.add_handler(
        MessageHandler(filters.COMMAND, _rate_limit_guard),
        group=-1,
    )

    # /start в группе — инициализация бота
    app.add_handler(CommandHandler("start", _group_start_command, filters=filters.ChatType.GROUPS))

    # В личке работают только /start, /help, /rate
    app.add_handler(CommandHandler("start",    _private_start,  filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("help",     help_command))
    app.add_handler(CommandHandler("rate",     rate_command))

    # Команды только для групп
    app.add_handler(CommandHandler("debug",   debug_command))
    app.add_handler(CommandHandler("dice",    dice_command,    filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("roast",   roast_command,   filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("top",     top_command,     filters=filters.ChatType.GROUPS))

    # MGE
    app.add_handler(CommandHandler("mge",   mge_command,   filters=filters.ChatType.GROUPS))


    # Личная статистика
    app.add_handler(CommandHandler("stats",         stats_command,         filters=filters.ChatType.GROUPS))

    # Ачивки — работает в группах (показывает редирект) и в личке (меню)
    app.add_handler(CommandHandler("achievements",  achievements_command))

    # Анонимные сообщения в группу
    app.add_handler(CommandHandler("anon",   anon_command,   filters=filters.ChatType.GROUPS))
    # Единый /cancel — сначала проверяем resend, потом anon
    async def _cancel_command(update, context):
        from commands.resend import _RESEND_WAITING
        if update.effective_user.id in _RESEND_WAITING:
            await resend_cancel(update, context)
        else:
            await handle_anon_cancel(update, context)

    app.add_handler(CommandHandler("cancel", _cancel_command, filters=filters.ChatType.PRIVATE))

    app.add_handler(CommandHandler("gallery",    gallery_command,    filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("clearmedia", clearmedia_command))

    # Скрытые команды владельца — только в личке, не в списке команд
    app.add_handler(CommandHandler("delmsg",       delmsg_command,       filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("resend",       resend_command,       filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("settings",     settings_command,     filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("exportstats",  exportstats_command,  filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("backup",       backup_command,       filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("clearstats",   clearstats_command,   filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("maintenance",  maintenance_command,  filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("restart",      restart_command,      filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("dashboard",    dashboard_command))
    app.add_handler(CommandHandler("ownerhelp",    ownerhelp_command))
    app.add_handler(CommandHandler("botset",       botset_command,       filters=filters.ChatType.PRIVATE))

    # Утилиты владельца (только в личке)
    app.add_handler(CommandHandler("synccmds", synccmds_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("giveach",   giveach_command,   filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("revokeach", revokeach_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("announce",  announce_command,  filters=filters.ChatType.PRIVATE))

    # Ловим любые другие команды в личке и вежливо отказываем
    app.add_handler(MessageHandler(
        filters.COMMAND & filters.ChatType.PRIVATE,
        _private_command_guard,
    ))

    # Неизвестные команды в группе
    async def _unknown_command(update, context):
        await update.message.reply_text("Сосунок я таких слов не знаю!")

    app.add_handler(MessageHandler(
        filters.COMMAND & filters.ChatType.GROUPS,
        _unknown_command,
    ))

    # Автоопределение CHAT_ID при добавлении бота в группу
    app.add_handler(ChatMemberHandler(_on_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))

    # Видео в личке для /rate
    app.add_handler(MessageHandler(
        filters.VIDEO & filters.ChatType.PRIVATE,
        handle_rate_video,
    ))

    # Кнопка «Закрыть» в уведомлении об итогах голосования
    async def _dismiss_callback(update, context):
        await update.callback_query.answer()
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass

    # Inline-кнопки
    app.add_handler(CallbackQueryHandler(_dismiss_callback,      pattern=r"^dismiss$"))
    app.add_handler(CallbackQueryHandler(delmsg_callback,        pattern=r"^delmsg_"))
    app.add_handler(CallbackQueryHandler(settings_callback,      pattern=r"^stg:"))
    app.add_handler(CallbackQueryHandler(top_callback,           pattern=r"^top_"))
    app.add_handler(CallbackQueryHandler(rate_callback,          pattern=r"^(anon_|rate_|comment_ask_|comment_skip_)"))
    app.add_handler(CallbackQueryHandler(ownerhelp_pin_callback, pattern=r"^ownerhelp_pin$"))
    app.add_handler(CallbackQueryHandler(clearmedia_callback,    pattern=r"^clearmedia_"))
    app.add_handler(CallbackQueryHandler(clearstats_callback,    pattern=r"^clrstats:"))
    app.add_handler(CallbackQueryHandler(dashboard_callback,     pattern=r"^dash:"))
    app.add_handler(CallbackQueryHandler(achievements_callback,  pattern=r"^ach"))

    # Анонимные сообщения / подпись /rate / resend в личке + трекинг в группах
    async def _maybe_token_reply(update, context):
        if update.effective_chat and update.effective_chat.type == "private":
            # Приоритет: настройки → resend → подпись к /rate → анонимное сообщение
            if await handle_settings_input(update, context):
                return
            if await handle_resend_message(update, context):
                return
            if await handle_rate_comment(update, context):
                return
            await handle_anon_message(update, context)
        else:
            await track_message_handler(update, context)

    # Трекинг текстовых сообщений (без команд)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _maybe_token_reply))

    # Фото в личке: сначала смена аватара (/botset photo), потом /rate
    async def _private_photo_handler(update, context):
        if await handle_botset_photo(update, context):
            return
        await handle_rate_photo(update, context)

    app.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE,
        _private_photo_handler,
    ))

    # Отмена swear-job при редактировании сообщений (убрали мат → не отвечаем)
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, _handle_edited_message))

    async def on_startup(app):
        # Применяем шаблоны описания из bot_identity.json (если есть), иначе дефолт
        try:
            await apply_identity(app.bot, online=True)
        except Exception:
            await app.bot.set_my_description("Скаут на связи 🟢")
            await app.bot.set_my_short_description("Скаут на связи 🟢")
        await send_restart_done(app)
        await sync_bot_commands(app.bot)  # синхронизирует список команд с текущими настройками

        # Авто-восстановление дашборда: если монитор назначен, но панели не отправлены
        from commands.dashboard import setup_dashboard, _load_state, get_monitor_chat_id as _get_mon
        _mon_id = _get_mon()
        if _mon_id:
            _st = _load_state()
            _has_panels = any(_st.get(k) for k in ("status", "server", "stats", "activity"))
            if not _has_panels:
                logger.info("on_startup: дашборд не найден, авто-настройка для чата %s", _mon_id)
                async def _auto_setup(ctx):
                    await setup_dashboard(ctx.bot, _mon_id)
                app.job_queue.run_once(_auto_setup, 30, name="dashboard_auto_setup")

        msk = datetime.timezone(datetime.timedelta(hours=3))

        # Ночной отчёт о матах в 00:00 МСК
        midnight = datetime.time(0, 0, 0, tzinfo=msk)
        app.job_queue.run_daily(_midnight_swear_report, time=midnight, name="midnight_swear")
        logger.info("Ночной отчёт запланирован на 00:00 МСК")

        # Лучшее фото недели — каждый понедельник 00:00 МСК
        app.job_queue.run_daily(
            _weekly_best_photo,
            time=midnight,
            days=(0,),          # 0 = понедельник
            name="weekly_best_photo",
        )
        logger.info("Еженедельное лучшее фото запланировано на пн 00:00 МСК")

        # Авточистка файлов старше 30 дней — ежедневно в 03:00 МСК
        three_am = datetime.time(3, 0, 0, tzinfo=msk)
        app.job_queue.run_daily(_cleanup_old_photos, time=three_am, name="cleanup_old_photos")
        logger.info("Авточистка старых фото запланирована на 03:00 МСК")

        # Напоминание о стрике — ежедневно в 20:00 МСК
        eight_pm = datetime.time(20, 0, 0, tzinfo=msk)
        async def _streak_reminder(ctx):
            if not get_setting("streak_reminder"):
                return
            chat_id = get_main_chat_id()
            if not chat_id:
                return
            users = get_users_at_streak_risk(chat_id, min_streak=3)
            for u in users:
                pm = get_pm_chat(u["user_id"])
                if not pm:
                    continue
                try:
                    await ctx.bot.send_message(
                        pm,
                        f"⚠️ Твой стрик <b>{u['streak']} дн.</b> под угрозой!\n"
                        "Напиши что-нибудь в чат до полуночи, чтобы не потерять.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
        app.job_queue.run_daily(_streak_reminder, time=eight_pm, name="streak_reminder")
        logger.info("Напоминание о стрике запланировано на 20:00 МСК")

        # Топ недели — каждое воскресенье в 21:00 МСК
        nine_pm = datetime.time(21, 0, 0, tzinfo=msk)
        async def _weekly_top(ctx):
            if not get_setting("weekly_top"):
                return
            chat_id = get_main_chat_id()
            if not chat_id:
                return
            top = get_top_messages_since(chat_id, days=7, limit=3)
            if not top:
                return
            medals = ["🥇", "🥈", "🥉"]
            lines = ["📊 <b>Топ недели</b>\n"]
            for i, u in enumerate(top):
                lines.append(f"{medals[i]} {_html_mod.escape(u['first_name'] or 'Аноним')} — {u['total']} сообщ.")
            try:
                await ctx.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
            except Exception as e:
                logger.warning("weekly_top: %s", e)
        app.job_queue.run_daily(
            _weekly_top,
            time=nine_pm,
            days=(6,),  # 6 = воскресенье
            name="weekly_top",
        )
        logger.info("Топ недели запланирован на вс 21:00 МСК")

        # Авточистка in-memory словарей — каждый час убираем устаревшие записи
        async def _cleanup_cmd_cooldown(ctx):
            cutoff = time.time() - 7200
            stale = [k for k, v in _cmd_last_used.items() if v < cutoff]
            for k in stale:
                _cmd_last_used.pop(k, None)
            if stale:
                logger.debug("_cmd_last_used: удалено %d устаревших записей", len(stale))
            # Чистим in-memory состояние message_tracker (speedrun, реакции и т.д.)
            cleanup_state()

        app.job_queue.run_repeating(_cleanup_cmd_cooldown, interval=3600, first=3600, name="cleanup_cmd_cooldown")

        # Сброс кэша аватаров раз в 24 ч — чтобы обновлять фото профиля
        async def _clear_avatar_cache(ctx):
            clear_avatar_cache()

        app.job_queue.run_repeating(_clear_avatar_cache, interval=86400, first=86400, name="clear_avatar_cache")

        # Периодическое обновление дашборда мониторинга
        app.job_queue.run_repeating(
            dashboard_update_job,
            interval=DASHBOARD_UPDATE_INTERVAL,
            first=60,
            name="dashboard_update",
        )
        logger.info("Обновление дашборда запланировано каждые %ds", DASHBOARD_UPDATE_INTERVAL)

        # Авто-бэкап БД в монитор-чат каждый день в 04:00 МСК
        four_am = datetime.time(4, 0, 0, tzinfo=msk)

        async def _auto_backup(ctx):
            from chat_config import get_monitor_chat_id as _get_mon_bk
            mon_id = _get_mon_bk()
            if not mon_id:
                logger.info("auto_backup: монитор-чат не назначен, пропускаем")
                return
            if not os.path.exists(DATABASE_PATH):
                logger.warning("auto_backup: файл БД не найден")
                return
            size = os.path.getsize(DATABASE_PATH)
            size_str = (
                f"{size / 1024:.1f} КБ" if size < 1024 * 1024
                else f"{size / 1024 / 1024:.1f} МБ"
            )
            now_bk = datetime.datetime.now(msk)
            filename = f"backup_{now_bk.strftime('%Y-%m-%d')}.db"
            try:
                with open(DATABASE_PATH, "rb") as f:
                    await ctx.bot.send_document(
                        chat_id=mon_id,
                        document=f,
                        filename=filename,
                        caption=(
                            f"🗄 <b>Авто-бэкап БД</b>\n\n"
                            f"📅 {now_bk.strftime('%d.%m.%Y %H:%M')} МСК\n"
                            f"📦 Размер: {size_str}"
                        ),
                        parse_mode="HTML",
                    )
                logger.info("auto_backup: бэкап отправлен в чат %s (%s)", mon_id, size_str)
            except Exception as e:
                logger.error("auto_backup: ошибка при отправке: %s", e)

        app.job_queue.run_daily(_auto_backup, time=four_am, name="auto_backup")
        logger.info("Авто-бэкап БД запланирован на 04:00 МСК")

    async def on_shutdown(app):
        try:
            await apply_identity(app.bot, online=False)
        except Exception:
            try:
                await app.bot.set_my_description("Скаут недоступен 🔴")
                await app.bot.set_my_short_description("Скаут недоступен 🔴")
            except Exception:
                pass

    app.post_init = on_startup
    app.post_shutdown = on_shutdown

    logger.info("Бот запущен")
    app.run_polling(poll_interval=0, drop_pending_updates=True)


if __name__ == "__main__":
    main()
