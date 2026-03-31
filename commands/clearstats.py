# ==============================================================================
# commands/clearstats.py — /clearstats: очистка статистики чата (только владелец)
# Работает только в личке. Показывает список чатов с подтверждением.
# ==============================================================================

import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from chat_config import get_main_chat_id, get_monitor_chat_id, get_setup_chats
from database import clear_chat_stats
from config import OWNER_ID

logger = logging.getLogger(__name__)


async def clearstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/clearstats — показывает список чатов для выбора и очистки статистики."""
    if update.effective_user.id != OWNER_ID:
        return

    setup_chats = get_setup_chats()
    main_id     = get_main_chat_id()
    monitor_id  = get_monitor_chat_id()

    if not setup_chats and not main_id:
        await update.message.reply_text("Нет инициализированных чатов.")
        return

    # Собираем все известные group chat IDs
    all_ids = set(setup_chats)
    if main_id:
        all_ids.add(main_id)

    # Получаем названия чатов
    rows = []
    for cid in sorted(all_ids):
        if cid == monitor_id:
            continue  # монитор-чат пропускаем
        try:
            chat = await context.bot.get_chat(cid)
            title = html.escape(chat.title or str(cid))
        except Exception:
            title = str(cid)
        role = ""
        if cid == main_id:
            role = " 🟢"
        rows.append((cid, title, role))

    if not rows:
        await update.message.reply_text("Нет чатов для очистки.")
        return

    buttons = [
        [InlineKeyboardButton(f"🗑 {title}{role}", callback_data=f"clrstats:ask:{cid}")]
        for cid, title, role in rows
    ]
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="clrstats:cancel")])

    await update.message.reply_text(
        "🗑 <b>Очистка статистики</b>\n\n"
        "Выбери чат, статистику которого нужно <b>полностью очистить</b>:\n\n"
        "<i>Удалится: сообщения, маты, ачивки, стрики, история королей.\n"
        "Галерея фото НЕ затрагивается.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def clearstats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопок /clearstats."""
    query = update.callback_query
    if not query:
        return
    if query.from_user.id != OWNER_ID:
        await query.answer("🚫 Только для владельца.", show_alert=True)
        return

    data = query.data

    if data == "clrstats:cancel":
        await query.answer("Отменено.")
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if data.startswith("clrstats:ask:"):
        try:
            chat_id = int(data[13:])
        except ValueError:
            await query.answer("Ошибка данных.", show_alert=True)
            return

        try:
            chat = await context.bot.get_chat(chat_id)
            title = html.escape(chat.title or str(chat_id))
        except Exception:
            title = str(chat_id)

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, очистить", callback_data=f"clrstats:confirm:{chat_id}"),
                InlineKeyboardButton("❌ Отмена",       callback_data="clrstats:cancel"),
            ]
        ])
        await query.edit_message_text(
            f"⚠️ <b>Подтверждение</b>\n\n"
            f"Очистить всю статистику чата <b>{title}</b>?\n\n"
            f"Будет удалено:\n"
            f"• Счётчики сообщений и матов всех участников\n"
            f"• Все ачивки\n"
            f"• Стрики активности\n"
            f"• Дневная статистика матов\n"
            f"• История королей дня\n\n"
            f"<b>Это действие необратимо.</b>",
            parse_mode="HTML",
            reply_markup=kb,
        )
        await query.answer()
        return

    if data.startswith("clrstats:confirm:"):
        try:
            chat_id = int(data[17:])
        except ValueError:
            await query.answer("Ошибка данных.", show_alert=True)
            return

        await query.answer("⏳ Очищаю...")
        try:
            counts = clear_chat_stats(chat_id)
        except Exception as e:
            logger.error("clearstats: ошибка при очистке чата %s: %s", chat_id, e)
            await query.edit_message_text(f"❌ Ошибка при очистке: <code>{html.escape(str(e))}</code>",
                                          parse_mode="HTML")
            return

        total = sum(counts.values())
        details = "\n".join(
            f"  • {table}: {n} записей"
            for table, n in counts.items()
            if n > 0
        ) or "  • Данных не было"

        logger.info("clearstats: чат %s очищен, удалено %d записей: %s", chat_id, total, counts)
        await query.edit_message_text(
            f"✅ <b>Статистика очищена</b>\n\n"
            f"Удалено {total} записей:\n{details}",
            parse_mode="HTML",
        )
