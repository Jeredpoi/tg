# ==============================================================================
# commands/settings.py — /settings: панель настроек бота (только в личке, только владелец)
# ==============================================================================

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from chat_config import (
    get_main_chat_id, set_main_chat_id, unset_main_chat, is_main_chat,
    get_setup_chats, get_settings, get_setting, set_setting,
)
from config import OWNER_ID

logger = logging.getLogger(__name__)


# ── Клавиатуры ────────────────────────────────────────────────────────────────

def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Управление чатами", callback_data="stg:chats")],
        [InlineKeyboardButton("🤬 Мат-детекция", callback_data="stg:swear")],
        [InlineKeyboardButton("📊 Отчёты и рассылки", callback_data="stg:reports")],
        [InlineKeyboardButton("🗳 Голосование /rate", callback_data="stg:vote")],
        [InlineKeyboardButton("⏱ Кулдаун команд", callback_data="stg:cooldown")],
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

    await update.message.reply_text(
        _MAIN_TEXT,
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
        await query.edit_message_text(
            _MAIN_TEXT,
            parse_mode="HTML",
            reply_markup=_main_menu_kb(),
        )
        await query.answer()

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
        main_hint = f"\n\n🟢 Основная: <b>{main_name}</b>"
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
        f"💬 <b>{name}</b>\n\n"
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
