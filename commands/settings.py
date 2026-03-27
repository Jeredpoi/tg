# ==============================================================================
# commands/settings.py — /settings: панель настроек бота (только в личке, только владелец)
# ==============================================================================

import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from chat_config import (
    get_main_chat_id, set_main_chat_id, unset_main_chat, is_main_chat,
    get_setup_chats, get_settings, get_setting, set_setting,
    MANAGEABLE_COMMANDS, get_disabled_commands, disable_command, enable_command,
    is_command_enabled,
    MGE_CHARACTERS,
    get_custom_mge_phrases, add_custom_mge_phrase, delete_custom_mge_phrase,
    get_custom_swear_responses, add_custom_swear_response, delete_custom_swear_response,
)
from config import OWNER_ID

# ── Состояния диалога ввода ───────────────────────────────────────────────────
# Хранятся в context.user_data["stg_state"]
STATE_AWAIT_MGE_PHRASE   = "await_mge_phrase"    # ждём текст фразы
STATE_AWAIT_SWEAR_RESP   = "await_swear_resp"    # ждём текст ответа на мат

logger = logging.getLogger(__name__)


# ── Клавиатуры ────────────────────────────────────────────────────────────────

def _main_menu_kb() -> InlineKeyboardMarkup:
    disabled = get_disabled_commands()
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


def _back_to_menu_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ Главное меню", callback_data="stg:menu")


def _back_to_chats_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ К списку чатов", callback_data="stg:chats")


# ── Тексты ────────────────────────────────────────────────────────────────────

_MAIN_TEXT = (
    "⚙️ <b>Настройки бота</b>\n\n"
    "Выбери раздел:"
)


# ── Команда /settings ─────────────────────────────────────────────────────────

async def _build_main_text(context) -> str:
    """Генерирует текст главного экрана со сводкой текущего состояния."""
    import datetime

    # Основная группа
    main_id = get_main_chat_id()
    if main_id:
        try:
            chat = await context.bot.get_chat(main_id)
            main_line = f"✅ {chat.title}"
        except Exception:
            main_line = f"✅ <code>{main_id}</code>"
    else:
        main_line = "⚠️ не назначена"

    # Команды
    disabled = get_disabled_commands()
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

    # ── Мат-детекция ──
    elif data == "stg:swear":
        await _show_swear_settings(query)

    elif data == "stg:swear_toggle":
        current = get_setting("swear_detect")
        set_setting("swear_detect", not current)
        await query.answer(f"{'🔴 Выключено' if current else '🟢 Включено'}!")
        await _show_swear_settings(query)

    elif data.startswith("stg:swear_chance:"):
        value = float(data[17:])
        set_setting("swear_response_chance", value)
        await query.answer(f"Шанс: {int(value * 100)}%")
        await _show_swear_settings(query)

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
        await _show_swear_resp_menu(query)

    elif data == "stg:swear_resp_list":
        await _show_swear_resp_list(query)

    elif data.startswith("stg:swear_resp_del:"):
        idx = int(data[19:])
        delete_custom_swear_response(idx)
        await query.answer("🗑 Ответ удалён")
        await _show_swear_resp_list(query)


# ── Экраны чатов ──────────────────────────────────────────────────────────────

async def _show_chat_list(query, context) -> None:
    """Показывает список всех инициализированных групп."""
    setup_chats = get_setup_chats()
    main_id = get_main_chat_id()

    if not setup_chats:
        await query.edit_message_text(
            "💬 <b>Чаты бота</b>\n\n"
            "Бот ещё не инициализирован ни в одной группе.\n"
            "Добавь бота в группу и напиши /start.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[_back_to_menu_btn()]]),
        )
        await query.answer()
        return

    buttons = []
    for cid in sorted(setup_chats):
        try:
            chat = await context.bot.get_chat(cid)
            name = chat.title or str(cid)
        except Exception:
            name = str(cid)
        icon = "🟢" if cid == main_id else "⚪"
        buttons.append([InlineKeyboardButton(
            f"{icon} {name}",
            callback_data=f"stg:chat:{cid}",
        )])

    buttons.append([_back_to_menu_btn()])

    main_hint = ""
    if main_id:
        try:
            mc = await context.bot.get_chat(main_id)
            main_name = mc.title or str(main_id)
        except Exception:
            main_name = str(main_id)
        main_hint = f"\n\n🟢 Основная: <b>{html.escape(main_name)}</b>"
    else:
        main_hint = "\n\n⚠️ Основная группа не выбрана"

    await query.edit_message_text(
        f"💬 <b>Управление чатами</b>{main_hint}\n\n"
        "Нажми на чат чтобы изменить его роль:\n"
        "🟢 — основная группа (рассылки, /anon, /rate)\n"
        "⚪ — тестовая / без роли",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    await query.answer()


async def _show_chat_detail(query, context, chat_id: int) -> None:
    """Показывает информацию о конкретном чате и кнопки управления."""
    main_id = get_main_chat_id()
    is_main = (main_id == chat_id)

    try:
        chat = await context.bot.get_chat(chat_id)
        name = chat.title or str(chat_id)
        members = await context.bot.get_chat_member_count(chat_id)
        members_line = f"\n👥 Участников: {members}"
    except Exception:
        name = str(chat_id)
        members_line = ""

    role_text = "🟢 Основная" if is_main else "⚪ Тестовая / без роли"
    role_desc = (
        "Сюда идут: ночной отчёт, фото недели, /anon, /rate"
        if is_main else
        "Рассылки и /anon сюда не приходят"
    )

    if is_main:
        action_btn = InlineKeyboardButton(
            "⚪ Снять как основную",
            callback_data=f"stg:mk_test:{chat_id}",
        )
    else:
        action_btn = InlineKeyboardButton(
            "🟢 Сделать основной",
            callback_data=f"stg:mk_main:{chat_id}",
        )

    kb = InlineKeyboardMarkup([
        [action_btn],
        [_back_to_chats_btn()],
    ])

    await query.edit_message_text(
        f"💬 <b>{html.escape(name)}</b>\n\n"
        f"🆔 ID: <code>{chat_id}</code>{members_line}\n"
        f"Роль: {role_text}\n"
        f"<i>{role_desc}</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ── Экран мат-детекции ────────────────────────────────────────────────────────

async def _show_swear_settings(query) -> None:
    enabled = get_setting("swear_detect")
    chance = get_setting("swear_response_chance")

    status = "🟢 Включена" if enabled else "🔴 Выключена"
    toggle_text = "🔴 Выключить" if enabled else "🟢 Включить"

    chance_options = [
        (0.2, "20%"), (0.35, "35%"), (0.45, "45%"),
        (0.6, "60%"), (0.8, "80%"), (1.0, "100%"),
    ]
    chance_buttons = []
    for val, label in chance_options:
        prefix = "✅ " if abs(chance - val) < 0.01 else ""
        chance_buttons.append(InlineKeyboardButton(
            f"{prefix}{label}",
            callback_data=f"stg:swear_chance:{val}",
        ))

    # Разбиваем на ряды по 3
    rows = [chance_buttons[i:i+3] for i in range(0, len(chance_buttons), 3)]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_text, callback_data="stg:swear_toggle")],
        *rows,
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        f"🤬 <b>Мат-детекция</b>\n\n"
        f"Статус: {status}\n"
        f"Шанс ответа на мат: <b>{int(chance * 100)}%</b>\n\n"
        f"<i>Бот реагирует на маты случайным комментарием. "
        f"Здесь можно включить/выключить это и настроить частоту.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


# ── Экран отчётов ─────────────────────────────────────────────────────────────

async def _show_reports_settings(query) -> None:
    midnight = get_setting("midnight_report")
    weekly = get_setting("weekly_best_photo")

    midnight_icon = "🟢" if midnight else "🔴"
    weekly_icon = "🟢" if weekly else "🔴"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{midnight_icon} Ночной отчёт по матам",
            callback_data="stg:midnight_toggle",
        )],
        [InlineKeyboardButton(
            f"{weekly_icon} Лучшее фото недели",
            callback_data="stg:weekly_toggle",
        )],
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        "📊 <b>Отчёты и рассылки</b>\n\n"
        f"🌙 Ночной отчёт по матам: {midnight_icon} {'вкл' if midnight else 'выкл'}\n"
        f"📸 Лучшее фото недели: {weekly_icon} {'вкл' if weekly else 'выкл'}\n\n"
        "<i>Ночной отчёт — ежедневная статистика матов в 00:00.\n"
        "Фото недели — лучшее фото по рейтингу за неделю.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


# ── Экран голосования ─────────────────────────────────────────────────────────

async def _show_vote_settings(query) -> None:
    duration = get_setting("vote_duration")

    options = [15, 30, 45, 60]
    buttons = []
    for val in options:
        prefix = "✅ " if duration == val else ""
        buttons.append(InlineKeyboardButton(
            f"{prefix}{val} мин",
            callback_data=f"stg:vote_dur:{val}",
        ))

    kb = InlineKeyboardMarkup([
        buttons,
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        f"🗳 <b>Голосование /rate</b>\n\n"
        f"Длительность: <b>{duration} минут</b>\n\n"
        f"<i>Сколько длится голосование после публикации фото в группе.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


# ── Экран кулдауна ────────────────────────────────────────────────────────────

async def _show_cooldown_settings(query) -> None:
    cd = get_setting("cmd_cooldown")

    options = [5, 10, 15, 30]
    buttons = []
    for val in options:
        prefix = "✅ " if cd == val else ""
        buttons.append(InlineKeyboardButton(
            f"{prefix}{val} сек",
            callback_data=f"stg:cd:{val}",
        ))

    kb = InlineKeyboardMarkup([
        buttons,
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        f"⏱ <b>Кулдаун команд</b>\n\n"
        f"Интервал: <b>{cd} секунд</b>\n\n"
        f"<i>Минимальное время между использованиями одной команды "
        f"одним пользователем. Защищает от спама.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


# ── Экран управления командами ────────────────────────────────────────────────

async def _show_commands_settings(query) -> None:
    """Список команд с кнопками вкл/выкл."""
    rows = []
    for cmd, desc in MANAGEABLE_COMMANDS.items():
        enabled = is_command_enabled(cmd)
        icon = "🟢" if enabled else "🔴"
        rows.append([InlineKeyboardButton(
            f"{icon} {cmd} — {desc}",
            callback_data=f"stg:cmd_toggle:{cmd}",
        )])

    disabled_count = len(get_disabled_commands())
    status_line = (
        "Все команды включены" if disabled_count == 0
        else f"Отключено: {disabled_count}"
    )

    rows.append([_back_to_menu_btn()])

    await query.edit_message_text(
        f"🎮 <b>Управление командами</b>\n\n"
        f"Статус: {status_line}\n\n"
        f"Нажми на команду чтобы включить или выключить её.\n"
        f"🟢 — включена  🔴 — выключена",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


# ── Экраны MGE-фраз ───────────────────────────────────────────────────────────

async def _show_mge_menu(query) -> None:
    phrases = get_custom_mge_phrases()
    count = len(phrases)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить фразу", callback_data="stg:mge_add")],
        [InlineKeyboardButton(
            f"📋 Мои фразы ({count})" if count else "📋 Фраз пока нет",
            callback_data="stg:mge_list",
        )],
        [_back_to_menu_btn()],
    ])
    await query.edit_message_text(
        f"✏️ <b>Фразы /mge</b>\n\n"
        f"Добавлено своих фраз: <b>{count}</b>\n\n"
        f"<i>Кастомные фразы добавляются к стандартным и выпадают случайно так же.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


async def _show_mge_char_picker(query) -> None:
    """Экран выбора персонажа перед вводом фразы."""
    rows = []
    for i in range(0, len(MGE_CHARACTERS), 2):
        row = [
            InlineKeyboardButton(MGE_CHARACTERS[i], callback_data=f"stg:mge_char:{MGE_CHARACTERS[i]}"),
        ]
        if i + 1 < len(MGE_CHARACTERS):
            row.append(InlineKeyboardButton(MGE_CHARACTERS[i+1], callback_data=f"stg:mge_char:{MGE_CHARACTERS[i+1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data="stg:mge")])

    await query.edit_message_text(
        "✏️ <b>Фразы /mge</b> — выбери персонажа\n\n"
        "От чьего имени будет звучать фраза?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


async def _show_mge_list(query) -> None:
    """Список кастомных фраз с кнопками удаления."""
    phrases = get_custom_mge_phrases()
    if not phrases:
        await query.edit_message_text(
            "✏️ <b>Фразы /mge</b>\n\nСвоих фраз пока нет.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Назад", callback_data="stg:mge"),
            ]]),
        )
        await query.answer()
        return

    rows = []
    for i, p in enumerate(phrases):
        short = p["phrase"][:35] + ("…" if len(p["phrase"]) > 35 else "")
        rows.append([InlineKeyboardButton(
            f"🗑 [{p['char']}] {short}",
            callback_data=f"stg:mge_del:{i}",
        )])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="stg:mge")])

    await query.edit_message_text(
        f"✏️ <b>Свои фразы /mge</b> ({len(phrases)} шт.)\n\n"
        f"Нажми на фразу чтобы удалить её:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


# ── Экраны кастомных ответов на маты ─────────────────────────────────────────

async def _show_swear_resp_menu(query) -> None:
    responses = get_custom_swear_responses()
    count = len(responses)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить ответ", callback_data="stg:swear_resp_add")],
        [InlineKeyboardButton(
            f"📋 Мои ответы ({count})" if count else "📋 Ответов пока нет",
            callback_data="stg:swear_resp_list",
        )],
        [_back_to_menu_btn()],
    ])
    await query.edit_message_text(
        f"💬 <b>Ответы на маты</b>\n\n"
        f"Добавлено своих ответов: <b>{count}</b>\n\n"
        f"<i>Используй <code>{{name}}</code> чтобы вставить имя матерщинника.\n"
        f"Кастомные ответы добавляются к стандартным и выпадают случайно.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


async def _show_swear_resp_list(query) -> None:
    responses = get_custom_swear_responses()
    if not responses:
        await query.edit_message_text(
            "💬 <b>Ответы на маты</b>\n\nСвоих ответов пока нет.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Назад", callback_data="stg:swear_resp"),
            ]]),
        )
        await query.answer()
        return

    rows = []
    for i, r in enumerate(responses):
        short = r[:40] + ("…" if len(r) > 40 else "")
        rows.append([InlineKeyboardButton(
            f"🗑 {short}",
            callback_data=f"stg:swear_resp_del:{i}",
        )])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="stg:swear_resp")])

    await query.edit_message_text(
        f"💬 <b>Свои ответы на маты</b> ({len(responses)} шт.)\n\n"
        f"Нажми на ответ чтобы удалить его:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


# ── Экран автоудаления ────────────────────────────────────────────────────────

_AUTODEL_OPTIONS = [0, 10, 15, 20, 25, 30, 60]  # 0 = выкл

def _autodel_row(setting_key: str, cb_prefix: str, label: str) -> list:
    """Строка кнопок для одной настройки автоудаления."""
    current = get_setting(setting_key)
    btns = []
    for val in _AUTODEL_OPTIONS:
        tick = "✅ " if current == val else ""
        txt  = "выкл" if val == 0 else f"{val}с"
        btns.append(InlineKeyboardButton(f"{tick}{txt}", callback_data=f"{cb_prefix}{val}"))
    return btns


async def _show_autodel_settings(query) -> None:
    h  = get_setting("autodel_help")
    g  = get_setting("autodel_gallery")
    ow = get_setting("autodel_ownerhelp")

    def fmt(v): return "выкл" if v == 0 else f"{v} сек."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 /help", callback_data="dismiss")],
        _autodel_row("autodel_help",      "stg:adh:",  "/help"),
        [InlineKeyboardButton("🖼 Галерея (личка)", callback_data="dismiss")],
        _autodel_row("autodel_gallery",   "stg:adg:",  "галерея"),
        [InlineKeyboardButton("👑 /ownerhelp", callback_data="dismiss")],
        _autodel_row("autodel_ownerhelp", "stg:adow:", "/ownerhelp"),
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        "🗑 <b>Автоудаление сообщений</b>\n\n"
        f"📖 /help: <b>{fmt(h)}</b>\n"
        f"🖼 Галерея (личка): <b>{fmt(g)}</b>\n"
        f"👑 /ownerhelp: <b>{fmt(ow)}</b>\n\n"
        "<i>Сколько секунд показывается сообщение перед удалением.\n"
        "«выкл» — сообщение не удаляется.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


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

    return False
