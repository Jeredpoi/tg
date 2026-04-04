# ==============================================================================
# commands/help.py — Команда /help + /ownerhelp
# ==============================================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import OWNER_ID
from chat_config import get_setting

HELP_TEXT = """
🤖 <b>Команды бота</b>

🎲 <b>Развлечения</b>
/dice — бросить кубик
/roast @user — подколоть участника (или ответом на сообщение)
/mge — случайная фраза из МГЕ (можно ответом на сообщение)

📊 <b>Статистика</b>
/top — топ активности, матов и рейтинга /rate
/stats — личная статистика (или ответом — чужая)
/achievements — твои достижения и прогресс

📸 <b>Медиа</b>
/rate — отправить фото или видео на оценку группы (в личке боту)
/gallery — открыть галерею фото и видео

🎭 <b>Анонимка</b>
/anon — отправить анонимное сообщение в группу (бот спросит в личке)

<b>Прочее</b>
/help — это сообщение
""".strip()

OWNER_HELP_TEXT = """
👑 <b>Команды владельца</b>

⚙️ <b>Управление ботом</b>
/settings — панель настроек бота (только в личке)
/synccmds — синхронизировать команды с Bot Father (только в личке)
/maintenance on|off — режим обслуживания
/restart — перезапустить бота (только в личке)
/delmsg — удалить сообщения бота из истории (только в личке)
/resend — отправить сообщение от имени бота в группу (только в личке)
/announce &lt;текст&gt; — объявление в основной чат (только в личке)
/clearmedia — очистить все фото/видео из галереи
/exportstats — выгрузить статистику в ZIP (только в личке)
/backup — резервная копия базы данных (только в личке)
/clearstats — очистить статистику чата
/dashboard — панели мониторинга в монитор-группу

🤖 <b>Кастомизация</b>
/botset — установить аватар, описание, имя бота

🛠 <b>Диагностика</b>
/debug — статус систем, чат-ID, права бота (удаляется через 20с)

🔨 <b>Модерация</b> <i>(в группе, ответом на сообщение)</i>
/ban [причина] — забанить участника
/kick — выгнать без бана
/mute [время] — замутить (10m, 2h, 1d)
/unmute — снять мут
/pin — закрепить сообщение
/unpin — открепить закреплённое

🏆 <b>Ачивки</b>
/giveach &lt;user_id&gt; &lt;chat_id&gt; &lt;ach_id&gt; — выдать ачивку вручную (личка)

━━━━━━━━━━━━━━━━━━━━━━━
👥 <b>Публичные команды</b>

🎲 /dice · /roast · /mge
📊 /top · /stats · /achievements
📸 /rate · /gallery
🎭 /anon
❓ /help
""".strip()

# chat_id → message_id закреплённого /ownerhelp
_pinned_ownerhelp: dict[int, int] = {}


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команд /help и /start. Автоудаляется если autodel_help > 0."""
    user_msg = update.message
    chat     = update.effective_chat
    in_group = chat and chat.type in ("group", "supergroup")

    # Сначала отправляем ответ, потом удаляем команду
    bot_msg = await context.bot.send_message(
        chat_id=user_msg.chat_id,
        text=HELP_TEXT,
        parse_mode="HTML",
    )

    if in_group:
        try:
            await user_msg.delete()
        except Exception:
            pass

    delay = get_setting("autodel_help")
    if delay:
        chat_id = user_msg.chat_id
        bot_mid = bot_msg.message_id

        async def _delete(ctx):
            try:
                await ctx.bot.delete_message(chat_id, bot_mid)
            except Exception:
                pass

        context.job_queue.run_once(_delete, delay)


async def ownerhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ownerhelp — список всех команд для владельца."""
    if update.effective_user.id != OWNER_ID:
        return
    user_msg = update.message
    # Удаляем команду сразу
    try:
        await user_msg.delete()
    except Exception:
        pass
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📌 Закрепить", callback_data="ownerhelp_pin"),
    ]])
    bot_msg = await user_msg.reply_text(OWNER_HELP_TEXT, parse_mode="HTML", reply_markup=kb)

    delay = get_setting("autodel_ownerhelp")
    if delay:
        chat_id  = user_msg.chat_id
        user_mid = user_msg.message_id
        bot_mid  = bot_msg.message_id

        async def _delete(ctx):
            for mid in [user_mid, bot_mid]:
                try:
                    await ctx.bot.delete_message(chat_id, mid)
                except Exception:
                    pass

        context.job_queue.run_once(_delete, delay)


async def ownerhelp_pin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки «Закрепить» в /ownerhelp."""
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("🚫 Только для владельца.", show_alert=True)
        return

    chat_id = query.message.chat_id
    msg_id  = query.message.message_id

    # Открепляем и удаляем старое закреплённое ownerhelp-сообщение
    old_id = _pinned_ownerhelp.get(chat_id)
    if old_id and old_id != msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id, old_id)
        except Exception:
            pass
        try:
            await context.bot.delete_message(chat_id, old_id)
        except Exception:
            pass

    # Закрепляем текущее сообщение
    try:
        await context.bot.pin_chat_message(chat_id, msg_id, disable_notification=True)
        _pinned_ownerhelp[chat_id] = msg_id
        # Убираем кнопку — сообщение теперь закреплено
        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer("📌 Закреплено!")
    except Exception as e:
        await query.answer(f"❌ Ошибка: {e}", show_alert=True)
