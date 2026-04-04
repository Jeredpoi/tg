# ==============================================================================
# commands/settings/_core.py — main command, callback dispatcher, input handler
# ==============================================================================

import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ._shared import (
    html, InlineKeyboardMarkup, InlineKeyboardButton,
    get_main_chat_id, get_monitor_chat_id, set_main_chat_id,
    set_monitor_chat_id, unset_main_chat, unset_monitor_chat,
    is_main_chat, is_monitor_chat, get_setup_chats,
    get_setting, set_setting, get_disabled_commands,
    disable_command, enable_command, is_command_enabled,
    sync_bot_commands, get_custom_mge_phrases,
    add_custom_mge_phrase, delete_custom_mge_phrase,
    get_custom_swear_responses, add_custom_swear_response,
    delete_custom_swear_response, get_custom_swear_triggers,
    add_custom_swear_trigger, delete_custom_swear_trigger,
    OWNER_ID, logger,
    STATE_AWAIT_MGE_PHRASE, STATE_AWAIT_SWEAR_RESP,
    STATE_AWAIT_TRIGGER_WORD, STATE_AWAIT_TRIGGER_RESP,
    _back_to_menu_btn, _back_to_chats_btn,
    MANAGEABLE_COMMANDS,
)
from ._screens import (
    _show_chat_list, _show_chat_detail,
    _show_swear_settings, _show_swear_triggers_menu, _show_swear_triggers_list,
    _show_reports_settings, _show_vote_settings, _show_cooldown_settings,
    _show_commands_settings,
    _show_mge_menu, _show_mge_char_picker, _show_mge_list,
    _show_swear_resp_menu, _show_swear_resp_list,
    _show_autodel_settings,
)


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _fmt_dur(v: int) -> str:
    if v == 0:    return "выкл"
    if v < 60:    return f"{v}с"
    if v < 3600:  return f"{v // 60}м"
    return f"{v // 3600}ч"


# ── Клавиатуры ────────────────────────────────────────────────────────────────

def _main_menu_kb() -> InlineKeyboardMarkup:
    disabled = get_disabled_commands() & set(MANAGEABLE_COMMANDS.keys())
    cmd_icon = "🔴" if disabled else "🟢"
    custom_mge   = len(get_custom_mge_phrases())
    custom_swear = len(get_custom_swear_responses())
    mge_badge   = f" ({custom_mge})"   if custom_mge   else ""
    swear_badge = f" ({custom_swear})" if custom_swear else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Управление чатами",              callback_data="stg:chats")],
        [InlineKeyboardButton(f"{cmd_icon} Команды бота",          callback_data="stg:cmds")],
        [InlineKeyboardButton("🤬 Мат-детекция",                   callback_data="stg:swear")],
        [InlineKeyboardButton(f"✏️ Фразы /mge{mge_badge}",         callback_data="stg:mge")],
        [InlineKeyboardButton(f"💬 Ответы на маты{swear_badge}",   callback_data="stg:swear_resp")],
        [InlineKeyboardButton("📊 Отчёты и рассылки",              callback_data="stg:reports")],
        [InlineKeyboardButton("🗳 Голосование /rate",               callback_data="stg:vote")],
        [InlineKeyboardButton("⏱ Кулдаун команд",                  callback_data="stg:cooldown")],
        [InlineKeyboardButton("🗑 Автоудаление сообщений",          callback_data="stg:autodel")],
        [InlineKeyboardButton("❌ Закрыть",                         callback_data="stg:close")],
    ])


# ── Тексты ────────────────────────────────────────────────────────────────────

async def _build_main_text(context) -> str:
    """Генерирует текст главного экрана со сводкой текущего состояния."""
    import datetime

    # Основная группа
    main_id = get_main_chat_id()
    if main_id:
        try:
            chat = await context.bot.get_chat(main_id)
            main_line = f"✅ {html.escape(chat.title or str(main_id))}"
        except Exception:
            main_line = f"✅ <code>{main_id}</code>"
    else:
        main_line = "⚠️ не назначена"

    # Команды
    disabled = get_disabled_commands() & set(MANAGEABLE_COMMANDS.keys())
    total_cmds = len(MANAGEABLE_COMMANDS)
    if disabled:
        cmds_line = f"🔴 Отключено {len(disabled)} из {total_cmds}"
    else:
        cmds_line = f"🟢 Все {total_cmds} включены"

    # Мат-детекция
    swear_on = get_setting("swear_detect")
    chance = int(get_setting("swear_response_chance") * 100)
    swear_line = f"🟢 вкл, шанс {chance}%" if swear_on else "🔴 выкл"

    # Отчёты
    midnight = get_setting("midnight_report")
    weekly = get_setting("weekly_best_photo")
    reports_parts = []
    if midnight:
        reports_parts.append("ночной")
    if weekly:
        reports_parts.append("фото недели")
    reports_line = ("🟢 " + ", ".join(reports_parts)) if reports_parts else "🔴 все выкл"

    # Голосование
    vote_dur = get_setting("vote_duration")

    # Кулдаун
    cd = get_setting("cmd_cooldown")

    # Автоудаление
    def _fmt_del(key):
        v = get_setting(key)
        return f"{v} сек." if v else "выкл"
    autodel_line = (
        f"/help {_fmt_del('autodel_help')} · "
        f"галерея {_fmt_del('autodel_gallery')} · "
        f"/ownerhelp {_fmt_del('autodel_ownerhelp')}"
    )

    # Кастомный контент
    custom_mge = len(get_custom_mge_phrases())
    custom_swear = len(get_custom_swear_responses())

    # Время
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    ts = now.strftime("%d.%m %H:%M МСК")

    return (
        f"⚙️ <b>Настройки бота</b>\n"
        f"<i>Обновлено: {ts}</i>\n\n"
        f"<b>Основная группа:</b> {main_line}\n"
        f"<b>Команды:</b> {cmds_line}\n"
        f"<b>Мат-детекция:</b> {swear_line}\n"
        f"<b>Отчёты:</b> {reports_line}\n"
        f"<b>Голосование:</b> {vote_dur} мин.\n"
        f"<b>Кулдаун:</b> {cd} сек.\n"
        f"<b>Свои фразы /mge:</b> {custom_mge} шт.\n"
        f"<b>Свои ответы на маты:</b> {custom_swear} шт.\n"
        f"<b>Автоудаление:</b> {autodel_line}\n\n"
        f"Выбери раздел:"
    )


# ── Команда /settings ─────────────────────────────────────────────────────────

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/settings — открывает панель настроек (только личка, только владелец)."""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Настройки доступны только владельцу.")
        return
    if update.effective_chat.type != "private":
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    # Удаляем команду пользователя для чистоты
    try:
        await update.message.delete()
    except Exception:
        pass

    text = await _build_main_text(context)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode="HTML",
        reply_markup=_main_menu_kb(),
    )


# ── Callback-обработчик ───────────────────────────────────────────────────────

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все нажатия кнопок панели настроек (stg:*)."""
    query = update.callback_query

    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Только для владельца.", show_alert=True)
        return

    data = query.data

    # ── Главное меню ──
    if data == "stg:menu":
        # Сбрасываем любой незавершённый диалог ввода
        context.user_data.pop("stg_state", None)
        context.user_data.pop("stg_mge_char", None)
        context.user_data.pop("stg_msg_id", None)
        text = await _build_main_text(context)
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=_main_menu_kb(),
        )
        await query.answer()

    # ── Заглушка для нажимаемых заголовков ──
    elif data == "stg:noop":
        await query.answer()

    # ── Закрыть панель ──
    elif data == "stg:close":
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass

    # ── Управление чатами ──
    elif data == "stg:chats":
        await _show_chat_list(query, context)

    elif data.startswith("stg:chat:"):
        try:
            chat_id = int(data[9:])
        except ValueError:
            await query.answer("Ошибка данных.", show_alert=True)
            return
        await _show_chat_detail(query, context, chat_id)

    elif data.startswith("stg:mk_main:"):
        try:
            chat_id = int(data[12:])
        except ValueError:
            await query.answer("Ошибка данных.", show_alert=True)
            return
        # Если чат является монитором — нельзя делать его основным
        if is_monitor_chat(chat_id):
            await query.answer(
                "⚠️ Этот чат уже монитор-группа. Сначала сними роль монитора.",
                show_alert=True,
            )
            return
        set_main_chat_id(chat_id)
        logger.info("settings: чат %s назначен основным", chat_id)
        await query.answer("✅ Чат назначен основным!")
        await _show_chat_detail(query, context, chat_id)

    elif data.startswith("stg:mk_test:"):
        try:
            chat_id = int(data[12:])
        except ValueError:
            await query.answer("Ошибка данных.", show_alert=True)
            return
        removed = unset_main_chat(chat_id)
        logger.info("settings: метка main снята с чата %s (была: %s)", chat_id, removed)
        await query.answer("✅ Метка «основной» снята." if removed else "ℹ️ Чат и так не основной.")
        await _show_chat_detail(query, context, chat_id)

    elif data.startswith("stg:mk_monitor:"):
        try:
            chat_id = int(data[15:])
        except ValueError:
            await query.answer("Ошибка данных.", show_alert=True)
            return

        # Если чат является основным — нельзя делать его монитором
        if is_main_chat(chat_id):
            await query.answer(
                "⚠️ Этот чат уже назначен основным. Сначала сними роль основного.",
                show_alert=True,
            )
            return

        set_monitor_chat_id(chat_id)
        logger.info("settings: чат %s назначен монитором", chat_id)
        await query.answer("🖥 Настраиваю дашборд...", show_alert=False)
        await _show_chat_detail(query, context, chat_id)

        # Отменяем предыдущие незавершённые задачи настройки дашборда для этого чата
        for _old in context.job_queue.get_jobs_by_name(f"dashboard_setup_{chat_id}"):
            _old.schedule_removal()

        from commands.dashboard import setup_dashboard
        _cid = chat_id

        async def _do_setup(ctx):
            await setup_dashboard(ctx.bot, _cid)

        context.job_queue.run_once(
            _do_setup,
            10,
            name=f"dashboard_setup_{chat_id}",
        )

    elif data.startswith("stg:mk_nomonitor:"):
        try:
            chat_id = int(data[17:])
        except ValueError:
            await query.answer("Ошибка данных.", show_alert=True)
            return
        removed = unset_monitor_chat(chat_id)
        logger.info("settings: метка monitor снята с чата %s (была: %s)", chat_id, removed)
        # Очищаем состояние дашборда чтобы старые панели не мешали
        if removed:
            from commands.dashboard import _load_state, _save_state
            st = _load_state()
            if st.get("chat_id") == chat_id:
                _save_state({})
                logger.info("settings: состояние дашборда очищено (chat_id=%s)", chat_id)
        await query.answer("✅ Роль монитора снята." if removed else "ℹ️ Чат и так не монитор.")
        await _show_chat_detail(query, context, chat_id)

    # ── Мат-детекция ──
    elif data == "stg:swear":
        await _show_swear_settings(query)

    elif data == "stg:swear_toggle":
        current = get_setting("swear_detect")
        set_setting("swear_detect", not current)
        await query.answer(f"{'🔴 Выключено' if current else '🟢 Включено'}!")
        await _show_swear_settings(query)

    elif data.startswith("stg:swear_chance:"):
        try:
            value = float(data[17:])
        except ValueError:
            await query.answer("Ошибка данных.", show_alert=True)
            return
        set_setting("swear_response_chance", value)
        await query.answer(f"Шанс: {int(value * 100)}%")
        await _show_swear_settings(query)

    elif data == "stg:swear_triggers":
        await _show_swear_triggers_menu(query)

    elif data == "stg:trigger_list":
        await _show_swear_triggers_list(query)

    elif data == "stg:trigger_add":
        context.user_data["stg_state"] = STATE_AWAIT_TRIGGER_WORD
        msg = await query.edit_message_text(
            "🎯 <b>Добавление слова-триггера</b>\n\n"
            "Напиши слово или фразу, на которую бот будет реагировать:\n\n"
            "<i>Регистр не важен. Бот найдёт это слово в любом сообщении.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="stg:swear_triggers"),
            ]]),
        )
        context.user_data["stg_msg_id"] = msg.message_id
        await query.answer()

    elif data.startswith("stg:trigger_del:"):
        try:
            idx = int(data[16:])
        except ValueError:
            await query.answer("Ошибка данных.", show_alert=True)
            return
        delete_custom_swear_trigger(idx)
        await query.answer("🗑 Слово удалено")
        await _show_swear_triggers_list(query)

    elif data == "stg:trigger_resp_yes":
        if not context.user_data.get("stg_trigger_word"):
            await query.answer("❌ Сессия устарела. Начни заново.", show_alert=True)
            await _show_swear_triggers_menu(query)
            return
        context.user_data["stg_state"] = STATE_AWAIT_TRIGGER_RESP
        msg = await query.edit_message_text(
            "💬 <b>Свой ответ на слово</b>\n\n"
            "Напиши ответ бота (используй <code>{name}</code> для упоминания пользователя):\n\n"
            f"<i>Пример: Ну и зачем ты написал это, {{name}}?</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⏭ Пропустить", callback_data="stg:trigger_resp_skip"),
            ]]),
        )
        context.user_data["stg_msg_id"] = msg.message_id
        await query.answer()

    elif data == "stg:trigger_resp_skip":
        word = context.user_data.pop("stg_trigger_word", None)
        context.user_data.pop("stg_state", None)
        context.user_data.pop("stg_msg_id", None)
        if not word:
            await query.answer("❌ Сессия устарела. Начни заново.", show_alert=True)
            await _show_swear_triggers_menu(query)
            return
        add_custom_swear_trigger(word, None)
        chance = int(get_setting("swear_response_chance") * 100)
        await query.edit_message_text(
            f"✅ Слово «{html.escape(word)}» добавлено!\n\n"
            f"Бот будет реагировать на него стандартными ответами "
            f"с шансом <b>{chance}%</b>.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К триггерам", callback_data="stg:swear_triggers"),
            ]]),
        )
        await query.answer("✅ Добавлено!")

    # ── Отчёты и рассылки ──
    elif data == "stg:reports":
        await _show_reports_settings(query)

    elif data == "stg:midnight_toggle":
        current = get_setting("midnight_report")
        set_setting("midnight_report", not current)
        await query.answer(f"{'🔴 Выключено' if current else '🟢 Включено'}!")
        await _show_reports_settings(query)

    elif data == "stg:weekly_toggle":
        current = get_setting("weekly_best_photo")
        set_setting("weekly_best_photo", not current)
        await query.answer(f"{'🔴 Выключено' if current else '🟢 Включено'}!")
        await _show_reports_settings(query)

    # ── Голосование ──
    elif data == "stg:vote":
        await _show_vote_settings(query)

    elif data.startswith("stg:vote_dur:"):
        value = int(data[13:])
        set_setting("vote_duration", value)
        await query.answer(f"Голосование: {value} мин.")
        await _show_vote_settings(query)

    # ── Кулдаун ──
    elif data == "stg:cooldown":
        await _show_cooldown_settings(query)

    elif data.startswith("stg:cd:"):
        value = int(data[7:])
        set_setting("cmd_cooldown", value)
        await query.answer(f"Кулдаун: {value} сек.")
        await _show_cooldown_settings(query)

    # ── Автоудаление ──
    elif data == "stg:autodel":
        await _show_autodel_settings(query)

    elif data.startswith("stg:adh:"):
        value = int(data[8:])
        set_setting("autodel_help", value)
        await query.answer("выкл" if value == 0 else f"/help: {value} сек.")
        await _show_autodel_settings(query)

    elif data.startswith("stg:adg:"):
        value = int(data[8:])
        set_setting("autodel_gallery", value)
        await query.answer("выкл" if value == 0 else f"Галерея: {value} сек.")
        await _show_autodel_settings(query)

    elif data.startswith("stg:adow:"):
        value = int(data[9:])
        set_setting("autodel_ownerhelp", value)
        await query.answer("выкл" if value == 0 else f"/ownerhelp: {value} сек.")
        await _show_autodel_settings(query)

    elif data.startswith("stg:adtop:"):
        value = int(data[10:])
        set_setting("autodel_top", value)
        await query.answer("выкл" if value == 0 else f"/top: {_fmt_dur(value)}")
        await _show_autodel_settings(query)

    elif data.startswith("stg:adst:"):
        value = int(data[9:])
        set_setting("autodel_stats", value)
        await query.answer("выкл" if value == 0 else f"/stats: {_fmt_dur(value)}")
        await _show_autodel_settings(query)

    elif data.startswith("stg:addc:"):
        value = int(data[9:])
        set_setting("autodel_dice", value)
        await query.answer("выкл" if value == 0 else f"/dice: {_fmt_dur(value)}")
        await _show_autodel_settings(query)

    elif data.startswith("stg:adro:"):
        value = int(data[9:])
        set_setting("autodel_roast", value)
        await query.answer("выкл" if value == 0 else f"/roast: {_fmt_dur(value)}")
        await _show_autodel_settings(query)

    elif data.startswith("stg:admge:"):
        value = int(data[10:])
        set_setting("autodel_mge", value)
        await query.answer("выкл" if value == 0 else f"/mge: {_fmt_dur(value)}")
        await _show_autodel_settings(query)

    # ── Управление командами ──
    elif data == "stg:cmds":
        await _show_commands_settings(query)

    elif data.startswith("stg:cmd_toggle:"):
        cmd = data[15:]  # напр. "/mge"
        if is_command_enabled(cmd):
            disable_command(cmd)
            await query.answer(f"🔴 {cmd} выключена")
        else:
            enable_command(cmd)
            await query.answer(f"🟢 {cmd} включена")
        await sync_bot_commands(context.bot)
        await _show_commands_settings(query)

    # ── Кастомные MGE-фразы ──
    elif data == "stg:mge":
        await _show_mge_menu(query)

    elif data == "stg:mge_add":
        await _show_mge_char_picker(query)

    elif data.startswith("stg:mge_char:"):
        char = data[13:]
        context.user_data["stg_state"] = STATE_AWAIT_MGE_PHRASE
        context.user_data["stg_mge_char"] = char
        context.user_data["stg_msg_id"] = query.message.message_id
        await query.edit_message_text(
            f"✏️ <b>Фразы /mge</b> — добавление\n\n"
            f"Персонаж: <b>{char}</b>\n\n"
            f"Напиши фразу для этого персонажа:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="stg:mge_cancel"),
            ]]),
        )
        await query.answer()

    elif data == "stg:mge_cancel":
        context.user_data.pop("stg_state", None)
        context.user_data.pop("stg_mge_char", None)
        context.user_data.pop("stg_msg_id", None)
        await _show_mge_menu(query)

    elif data == "stg:mge_list":
        await _show_mge_list(query)

    elif data.startswith("stg:mge_del:"):
        idx = int(data[12:])
        delete_custom_mge_phrase(idx)
        await query.answer("🗑 Фраза удалена")
        await _show_mge_list(query)

    # ── Кастомные ответы на маты ──
    elif data == "stg:swear_resp":
        await _show_swear_resp_menu(query)

    elif data == "stg:swear_resp_add":
        context.user_data["stg_state"] = STATE_AWAIT_SWEAR_RESP
        context.user_data["stg_msg_id"] = query.message.message_id
        await query.edit_message_text(
            "💬 <b>Ответы на маты</b> — добавление\n\n"
            "Напиши свой ответ. Используй <code>{name}</code> там где нужно вставить имя.\n\n"
            "Пример: <i>Полегче, {name}!</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="stg:swear_resp_cancel"),
            ]]),
        )
        await query.answer()

    elif data == "stg:swear_resp_cancel":
        context.user_data.pop("stg_state", None)
        context.user_data.pop("stg_msg_id", None)
        await _show_swear_resp_menu(query)

    elif data == "stg:swear_resp_list":
        await _show_swear_resp_list(query)

    elif data.startswith("stg:swear_resp_del:"):
        idx = int(data[19:])
        delete_custom_swear_response(idx)
        await query.answer("🗑 Ответ удалён")
        await _show_swear_resp_list(query)


# ── Обработчик текстового ввода из настроек ───────────────────────────────────

async def handle_settings_input(update: Update, context) -> bool:
    """
    Вызывается из _maybe_token_reply когда пользователь — владелец в личке.
    Возвращает True если сообщение было обработано как ввод настроек.
    """
    if update.effective_user.id != OWNER_ID:
        return False

    state = context.user_data.get("stg_state")
    if not state:
        return False

    text = (update.message.text or "").strip()

    # ── Ввод MGE-фразы ──
    if state == STATE_AWAIT_MGE_PHRASE:
        char = context.user_data.pop("stg_mge_char", "Игрок")
        context.user_data.pop("stg_state", None)

        if not text:
            await update.message.reply_text("❌ Пустая фраза. Попробуй снова через /settings.")
            return True
        if len(text) > 500:
            await update.message.reply_text("❌ Слишком длинная фраза (макс. 500 символов). Попробуй короче.")
            return True

        add_custom_mge_phrase(char, text)
        user_mid   = update.message.message_id
        prompt_mid = context.user_data.pop("stg_msg_id", None)
        bot_msg = await update.message.reply_text(
            f"✅ Фраза добавлена!\n\n"
            f"🎭 <b>{html.escape(char)}:</b>\n«{html.escape(text)}»",
            parse_mode="HTML",
        )
        bot_mid  = bot_msg.message_id
        chat_id  = update.message.chat_id

        async def _cleanup_mge(ctx):
            for mid in filter(None, [user_mid, prompt_mid, bot_mid]):
                try:
                    await ctx.bot.delete_message(chat_id, mid)
                except Exception:
                    pass

        context.job_queue.run_once(_cleanup_mge, 4)
        return True

    # ── Ввод ответа на мат ──
    if state == STATE_AWAIT_SWEAR_RESP:
        context.user_data.pop("stg_state", None)

        if not text:
            await update.message.reply_text("❌ Пустой ответ. Попробуй снова через /settings.")
            return True
        if len(text) > 300:
            await update.message.reply_text("❌ Слишком длинный ответ (макс. 300 символов). Попробуй короче.")
            return True

        add_custom_swear_response(text)
        try:
            preview = text.format(name="Вася") if "{name}" in text else text
        except (KeyError, IndexError):
            preview = text
        user_mid  = update.message.message_id
        prompt_mid = context.user_data.pop("stg_msg_id", None)
        bot_msg  = await update.message.reply_text(
            f"✅ Ответ добавлен!\n\n"
            f"Пример: <i>{html.escape(preview)}</i>",
            parse_mode="HTML",
        )
        bot_mid  = bot_msg.message_id
        chat_id  = update.message.chat_id

        async def _cleanup_swear(ctx):
            for mid in filter(None, [user_mid, prompt_mid, bot_mid]):
                try:
                    await ctx.bot.delete_message(chat_id, mid)
                except Exception:
                    pass

        context.job_queue.run_once(_cleanup_swear, 4)
        return True

    # ── Ввод слова-триггера ──
    if state == STATE_AWAIT_TRIGGER_WORD:
        if not text:
            await update.message.reply_text("❌ Пустое слово. Напиши слово ещё раз.")
            return True
        if len(text) > 100:
            await update.message.reply_text("❌ Слишком длинное слово (макс. 100 символов). Напиши ещё раз.")
            return True

        context.user_data.pop("stg_state", None)
        context.user_data["stg_trigger_word"] = text.lower().strip()
        user_mid   = update.message.message_id
        prompt_mid = context.user_data.pop("stg_msg_id", None)
        chat_id    = update.message.chat_id

        # Удаляем промпт и ввод пользователя
        for mid in filter(None, [user_mid, prompt_mid]):
            try:
                await context.bot.delete_message(chat_id, mid)
            except Exception:
                pass

        # Спрашиваем про кастомный ответ через новое сообщение
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Слово «<b>{html.escape(text.lower().strip())}</b>» принято!\n\n"
                 f"Хочешь добавить свой ответ бота на это слово?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Да, добавить ответ", callback_data="stg:trigger_resp_yes"),
                InlineKeyboardButton("⏭ Нет, пропустить",    callback_data="stg:trigger_resp_skip"),
            ]]),
        )
        context.user_data["stg_msg_id"] = msg.message_id
        return True

    # ── Ввод ответа на триггер ──
    if state == STATE_AWAIT_TRIGGER_RESP:
        if not text:
            context.user_data.pop("stg_state", None)
            word = context.user_data.pop("stg_trigger_word", None)
            await update.message.reply_text("❌ Пустой ответ. Слово сохранено без ответа.")
            if word:
                add_custom_swear_trigger(word, None)
            return True
        if len(text) > 300:
            await update.message.reply_text("❌ Слишком длинный ответ (макс. 300 символов). Напиши короче.")
            return True

        context.user_data.pop("stg_state", None)
        word = context.user_data.pop("stg_trigger_word", None)
        if word:
            add_custom_swear_trigger(word, text)

        try:
            preview = text.format(name="Вася") if "{name}" in text else text
        except (KeyError, IndexError):
            preview = text

        user_mid   = update.message.message_id
        prompt_mid = context.user_data.pop("stg_msg_id", None)
        chat_id    = update.message.chat_id
        chance     = int(get_setting("swear_response_chance") * 100)

        bot_msg = await update.message.reply_text(
            f"✅ Готово! Слово «<b>{html.escape(word or '?')}</b>» добавлено с ответом.\n\n"
            f"Пример ответа: <i>{html.escape(preview)}</i>\n\n"
            f"Бот будет реагировать с шансом <b>{chance}%</b>.",
            parse_mode="HTML",
        )
        bot_mid = bot_msg.message_id

        async def _cleanup_trigger(ctx):
            for mid in filter(None, [user_mid, prompt_mid, bot_mid]):
                try:
                    await ctx.bot.delete_message(chat_id, mid)
                except Exception:
                    pass

        context.job_queue.run_once(_cleanup_trigger, 5)
        return True

    return False
