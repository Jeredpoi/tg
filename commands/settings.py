# ==============================================================================
# commands/settings.py — /settings: панель настроек бота (только в личке, только владелец)
# ==============================================================================

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from chat_config import (
    get_main_chat_id, set_main_chat_id, unset_main_chat, is_main_chat,
    get_setup_chats,
)
from config import OWNER_ID

logger = logging.getLogger(__name__)


# ── Клавиатуры ────────────────────────────────────────────────────────────────

def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 Управление чатами", callback_data="stg:chats"),
    ]])


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

    if data == "stg:menu":
        await query.edit_message_text(
            _MAIN_TEXT,
            parse_mode="HTML",
            reply_markup=_main_menu_kb(),
        )
        await query.answer()

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


# ── Внутренние экраны ─────────────────────────────────────────────────────────

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
