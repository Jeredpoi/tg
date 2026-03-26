# ==============================================================================
# commands/delmsg.py — /delmsg: удаление последних сообщений бота (только для владельца)
# Работает ТОЛЬКО в личке. В списке команд не отображается.
# ==============================================================================

import logging
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    get_recent_bot_messages, get_all_bot_messages_recent,
    get_bot_message_count, get_all_bot_messages_count,
    delete_bot_message_record,
)
import config

logger = logging.getLogger(__name__)

# Сколько сообщений показывать на одной странице
PAGE_SIZE = 5


def _fmt_preview(preview: str, chat_id: int) -> str:
    """Форматирует превью сообщения с указанием чата."""
    text = (preview or "—").strip()
    # Обрезаем слишком длинный текст
    if len(text) > 50:
        text = text[:47] + "..."
    # Добавляем подсказку по чату (последние 6 цифр ID для краткости)
    chat_hint = f"[{str(chat_id)[-6:]}]"
    return f"{chat_hint} {text}"


def _build_keyboard(rows: list, page: int, total: int) -> InlineKeyboardMarkup:
    """Строит клавиатуру: кнопки удаления + навигация."""
    # Кнопки удаления (по одной в ряд для читаемости превью)
    delete_rows = []
    for i, row in enumerate(rows):
        num = page * PAGE_SIZE + i + 1
        # chat_id_msgid_page в callback_data
        cb = f"delmsg_del_{row['chat_id']}_{row['message_id']}_{page}"
        delete_rows.append([InlineKeyboardButton(
            f"🗑 {num}",
            callback_data=cb,
        )])

    # Навигация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"delmsg_pg_{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️ Ещё", callback_data=f"delmsg_pg_{page + 1}"))

    keyboard = delete_rows
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("❌ Закрыть", callback_data="delmsg_close")])
    return InlineKeyboardMarkup(keyboard)


def _build_text(rows: list, page: int, total: int) -> str:
    """Строит текст списка сообщений."""
    lines = [f"🗑 <b>Последние сообщения бота</b> (всего {total}):\n"]
    for i, row in enumerate(rows):
        num = page * PAGE_SIZE + i + 1
        # Форматируем время отправки
        try:
            dt = datetime.datetime.fromtimestamp(row["sent_at"]).strftime("%d.%m %H:%M")
        except Exception:
            dt = "?"
        preview = _fmt_preview(row["preview"], row["chat_id"])
        lines.append(f"<b>{num}.</b> <i>{dt}</i> — {preview}")
    return "\n".join(lines)


async def delmsg_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик /delmsg в личке. Только для владельца бота."""
    if update.effective_user.id != config.OWNER_ID:
        # Молча игнорируем — чужие не знают о команде
        return

    # Удаляем саму команду из лички для чистоты
    try:
        await update.message.delete()
    except Exception:
        pass

    rows = get_all_bot_messages_recent(offset=0, limit=PAGE_SIZE)
    total = get_all_bot_messages_count()

    if not rows:
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="📭 Нет сохранённых сообщений бота.",
        )
        # Автоудаление уведомления через 10 сек
        mid = msg.message_id
        cid = update.effective_chat.id

        async def _del(ctx):
            try:
                await ctx.bot.delete_message(cid, mid)
            except Exception:
                pass

        context.job_queue.run_once(_del, 10)
        return

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=_build_text(rows, 0, total),
        parse_mode="HTML",
        reply_markup=_build_keyboard(rows, 0, total),
    )


async def delmsg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик инлайн-кнопок команды /delmsg."""
    query = update.callback_query

    # Проверяем владельца
    if query.from_user.id != config.OWNER_ID:
        await query.answer("🚫 Только для владельца бота", show_alert=True)
        return

    data = query.data

    # ── Закрыть список ────────────────────────────────────────────────────
    if data == "delmsg_close":
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # ── Удалить конкретное сообщение ──────────────────────────────────────
    if data.startswith("delmsg_del_"):
        # Формат: delmsg_del_{chat_id}_{message_id}_{page}
        # chat_id может быть отрицательным, поэтому разбираем с конца
        parts = data.split("_")
        # parts = ['delmsg', 'del', chat_id_parts..., msg_id, page]
        # Последние два элемента — message_id и page
        try:
            page = int(parts[-1])
            msg_id = int(parts[-2])
            # Всё между "delmsg_del_" и последними двумя "_" — это chat_id
            chat_id = int("_".join(parts[2:-2]))
        except (ValueError, IndexError):
            await query.answer("❌ Ошибка разбора данных", show_alert=True)
            return

        await query.answer()

        # Удаляем сообщение из группы
        try:
            await context.bot.delete_message(chat_id, msg_id)
            logger.info("delmsg: удалено сообщение %s из чата %s", msg_id, chat_id)
        except Exception as e:
            logger.warning("delmsg: не удалось удалить %s/%s: %s", chat_id, msg_id, e)

        # Убираем запись из БД
        delete_bot_message_record(chat_id, msg_id)

        # Обновляем список
        rows = get_all_bot_messages_recent(offset=page * PAGE_SIZE, limit=PAGE_SIZE)
        total = get_all_bot_messages_count()

        # Если текущая страница опустела — откатываемся на предыдущую
        if not rows and page > 0:
            page -= 1
            rows = get_all_bot_messages_recent(offset=page * PAGE_SIZE, limit=PAGE_SIZE)

        if not rows:
            try:
                await query.edit_message_text("✅ Больше нет сохранённых сообщений.")
            except Exception:
                pass
            return

        try:
            await query.edit_message_text(
                _build_text(rows, page, total),
                parse_mode="HTML",
                reply_markup=_build_keyboard(rows, page, total),
            )
        except Exception as e:
            logger.warning("delmsg_callback edit: %s", e)

    # ── Переключение страницы ─────────────────────────────────────────────
    elif data.startswith("delmsg_pg_"):
        try:
            page = int(data.split("_")[-1])
        except ValueError:
            await query.answer()
            return

        await query.answer()

        rows = get_all_bot_messages_recent(offset=page * PAGE_SIZE, limit=PAGE_SIZE)
        total = get_all_bot_messages_count()

        if not rows:
            await query.answer("Больше нет сообщений.", show_alert=True)
            return

        try:
            await query.edit_message_text(
                _build_text(rows, page, total),
                parse_mode="HTML",
                reply_markup=_build_keyboard(rows, page, total),
            )
        except Exception as e:
            logger.warning("delmsg_callback page: %s", e)
