# ==============================================================================
# commands/achievements_cmd.py — /achievements: красивый просмотр ачивок
# ==============================================================================

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from commands.achievements import (
    ACHIEVEMENTS, CAT_EASY, CAT_HARD, CAT_SECRET,
    get_achievements_page, get_category_counts, get_user_close_achievements,
)

logger = logging.getLogger(__name__)

_PER_PAGE = 5

# Виртуальная «вкладка» — не настоящая категория ачивок
CAT_NEAR = "near"

_CAT_META = {
    CAT_EASY:   ("🟢", "Лёгкие"),
    CAT_HARD:   ("🔴", "Сложные"),
    CAT_SECRET: ("🔒", "Секретные"),
    CAT_NEAR:   ("🎯", "Близко"),
}
_CAT_ORDER = [CAT_EASY, CAT_HARD, CAT_SECRET, CAT_NEAR]
_REAL_CATS = {CAT_EASY, CAT_HARD, CAT_SECRET}


def _progress_bar(earned: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "░" * width
    filled = round(earned / total * width)
    return "▓" * filled + "░" * (width - filled)


def _pct(earned: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{round(earned / total * 100)}%"


def _build_near_text(user_id: int, chat_id: int, user_name: str = "") -> str:
    counts = get_category_counts(user_id, chat_id)
    items  = get_user_close_achievements(user_id, chat_id)

    name_str = f" · {user_name}" if user_name else ""
    header = f"🏅 <b>Ачивки{name_str}</b>\n"

    parts = []
    for cat in [CAT_EASY, CAT_HARD, CAT_SECRET]:
        e, t = counts[cat]
        em, _ = _CAT_META[cat]
        parts.append(f"{em} <b>{e}</b>/{t}")
    header += "  ·  ".join(parts)

    sep = "―" * 18
    section = f"\n{sep}\n🎯 <b>Ты близко</b>\n{sep}"

    if not items:
        body = "\n\n<i>Нет данных — начни использовать бота!</i>"
    else:
        lines = []
        for item in items:
            bar  = _progress_bar(item["current"], item["total"], width=8)
            pct  = round(item["pct"])
            left = item["total"] - item["current"]
            lines.append(
                f"\n{item['icon']} <b>{item['name']}</b>  <i>({pct}%)</i>\n"
                f"    <code>{bar}</code>  {item['current']}/{item['total']}"
                + (f"  · ещё {left}" if left > 0 else "")
            )
        body = "".join(lines)

    return header + section + body


def _build_page_text(
    user_id: int, chat_id: int,
    category: str, page: int,
    user_name: str = "",
) -> str:
    data    = get_achievements_page(user_id, chat_id, category, page, _PER_PAGE)
    counts  = get_category_counts(user_id, chat_id)
    items   = data["items"]
    cur     = data["page"]
    total_p = data["total_pages"]
    earned  = data["earned_count"]
    total   = data["total_count"]

    emoji, cat_label = _CAT_META[category]

    # ── Шапка ────────────────────────────────────────────────────────────────
    name_str = f" · {user_name}" if user_name else ""
    header = f"🏅 <b>Ачивки{name_str}</b>\n"

    parts = []
    for cat in [CAT_EASY, CAT_HARD, CAT_SECRET]:
        e, t = counts[cat]
        em, _ = _CAT_META[cat]
        parts.append(f"{em} <b>{e}</b>/{t}")
    header += "  ·  ".join(parts)

    # ── Раздел ───────────────────────────────────────────────────────────────
    bar      = _progress_bar(earned, total)
    pct      = _pct(earned, total)
    page_str = f"стр. {cur + 1}/{total_p}" if total_p > 1 else ""

    sep = "―" * 18
    section = (
        f"\n{sep}\n"
        f"{emoji} <b>{cat_label}</b>"
        + (f"  ·  {page_str}" if page_str else "")
        + f"\n<code>{bar}</code>  {earned} из {total}  <i>({pct})</i>\n"
        f"{sep}"
    )

    # ── Список ачивок ────────────────────────────────────────────────────────
    ach_lines = []
    for item in items:
        rarity = item.get("rarity")
        rarity_str = f"  <i>👥 {rarity}%</i>" if rarity is not None else ""

        if item["earned"]:
            first_str = " ⭐" if item.get("is_first") else ""
            ach_lines.append(
                f"\n✅ {item['icon']} <b>{item['name']}</b>{first_str}{rarity_str}\n"
                f"    <i>{item['desc']}</i>"
            )
        elif item["secret"]:
            ach_lines.append(
                f"\n🔒 <b>???</b>\n"
                f"    <i>{item['hint']}</i>"
            )
        else:
            ach_lines.append(
                f"\n⬜ {item['icon']} <b>{item['name']}</b>{rarity_str}\n"
                f"    <i>{item['hint']}</i>"
            )

    return header + section + "".join(ach_lines)


def _build_keyboard(
    category: str, page: int, total_pages: int,
    counts: dict,
) -> InlineKeyboardMarkup:
    rows = []

    # Ряд категорий — у каждой счётчик earned/total (кроме «Близко»)
    cat_row = []
    for cat in _CAT_ORDER:
        emoji, label = _CAT_META[cat]
        if cat == CAT_NEAR:
            btn_label = f"{emoji} {label}"
        else:
            e, t = counts.get(cat, (0, 0))
            btn_label = f"{emoji} {e}/{t}"
        if cat == category:
            btn_label = "✅ " + btn_label
        cat_row.append(InlineKeyboardButton(btn_label, callback_data=f"ach:{cat}:0"))
    rows.append(cat_row)

    # Ряд навигации (только для реальных категорий и если > 1 страницы)
    if category in _REAL_CATS and total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀", callback_data=f"ach:{category}:{page - 1}"))
        nav_row.append(InlineKeyboardButton(
            f"· {page + 1} / {total_pages} ·",
            callback_data="ach_page",
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("▶", callback_data=f"ach:{category}:{page + 1}"))
        rows.append(nav_row)

    return InlineKeyboardMarkup(rows)


async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/achievements — просмотр ачивок с пагинацией."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not update.message:
        return

    try:
        await update.message.delete()
    except Exception:
        pass

    category  = CAT_EASY
    page      = 0
    user_name = user.first_name or user.username or ""

    counts = get_category_counts(user.id, chat.id)
    data   = get_achievements_page(user.id, chat.id, category, page, _PER_PAGE)
    text   = _build_page_text(user.id, chat.id, category, page, user_name)
    kb     = _build_keyboard(category, page, data["total_pages"], counts)

    await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        parse_mode="HTML",
        reply_markup=kb,
    )


async def achievements_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопок: ach:<category>:<page>  или  ach_page (заглушка)."""
    query = update.callback_query
    if not query:
        return

    # Заглушка — индикатор страницы, ничего не делаем
    if query.data == "ach_page":
        await query.answer()
        return

    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "ach":
        return

    _, category, page_str = parts
    if category not in _CAT_META:
        return
    try:
        page = int(page_str)
    except ValueError:
        return

    user      = query.from_user
    chat      = query.message.chat
    user_name = user.first_name or user.username or ""
    counts    = get_category_counts(user.id, chat.id)

    # ── «Ты близко» — специальная вкладка ────────────────────────────────────
    if category == CAT_NEAR:
        text = _build_near_text(user.id, chat.id, user_name)
        kb   = _build_keyboard(CAT_NEAR, 0, 1, counts)
        try:
            await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.debug("achievements_callback near: %s", e)
        return

    # ── Обычная категория ────────────────────────────────────────────────────
    data = get_achievements_page(user.id, chat.id, category, page, _PER_PAGE)
    text = _build_page_text(user.id, chat.id, category, page, user_name)
    kb   = _build_keyboard(category, data["page"], data["total_pages"], counts)

    try:
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("achievements_callback: не удалось обновить: %s", e)
