# ==============================================================================
# commands/king.py — /king и королевские команды (/kfine, /kpardon, /kdecree)
# ==============================================================================

import random
from telegram import Update
from telegram.ext import ContextTypes
from database import get_all_users, get_king_today, set_king_today

_CROWN_MESSAGES = [
    "Случайный жребий брошен! Встречайте нового повелителя!",
    "Судьба распорядилась — трон занят!",
    "Боги определили своего избранника!",
    "Великий рандом сказал своё слово!",
]

_FINE_TEMPLATES = [
    "Королевским указом {king} штрафует {user} на 100 золотых!\nПричина: {reason}",
    "По воле короля {king} — {user} приговорён к трём дням без мемов!\nПричина: {reason}",
    "Его Величество {king} объявляет {user} персоной нон грата! Позор!\nПричина: {reason}",
    "Глашатай объявляет: {user} оштрафован королём {king}!\nПричина: {reason}",
]

_PARDON_TEMPLATES = [
    "Его Величество {king} великодушно прощает {user}! Ликуйте!",
    "Королевская милость снизошла на {user} — {king} прощает все грехи!",
    "{king} проявил мудрость и помиловал {user}. Слава королю!",
    "{user} помилован! {king} сегодня добр как никогда!",
]

_REWARD_TEMPLATES = [
    "Великий {king} награждает {user} орденом «За заслуги перед чатом»! Аплодисменты!",
    "По воле короля {king} — {user} удостоен королевской награды! Носи с честью!",
    "{king} лично отмечает {user} за выдающееся поведение! Да здравствует {user}!",
    "Королевским указом {king} вручает {user} титул «Лучший подданный»! Слава!",
]

_TAX_TEMPLATES = [
    "Королевский казначей объявляет: по указу {king} все платят налог! Казна пустовать не должна!",
    "Его Величество {king} вводит новый налог! Платить немедленно, иначе — в темницу!",
    "{king} объявляет налоговую проверку! Кто не заплатит — тот предатель престола!",
    "По велению {king} объявляется сбор налогов! Казна ждёт ваши монеты!",
]


def _king_mention(king_row) -> str:
    return f"@{king_row['username']}" if king_row['username'] else king_row['first_name']


async def king_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /king — выбрать короля дня.
    Можно выбрать только один раз в день на чат.
    Если король уже есть — показывает кто.
    """
    chat_id = update.effective_chat.id
    existing = get_king_today(chat_id)

    if existing:
        name = _king_mention(existing)
        await update.message.reply_text(
            f"Сегодняшний король уже выбран — это {name}!\n\n"
            f"Трон занят до завтра.\n"
            f"Королевские команды (только для него):\n"
            f"• /kfine @user [причина] — оштрафовать\n"
            f"• /kpardon @user — помиловать\n"
            f"• /kdecree <текст> — издать указ"
        )
        return

    users = get_all_users(chat_id)
    eligible = [u for u in users if u["username"] or u["first_name"]]

    if not eligible:
        await update.message.reply_text(
            "В базе нет пользователей.\n"
            "Пусть участники чата сначала напишут что-нибудь!"
        )
        return

    winner = random.choice(eligible)
    set_king_today(chat_id, winner["user_id"], winner["username"], winner["first_name"])

    mention = f"@{winner['username']}" if winner['username'] else winner['first_name']
    text = (
        f"👑 Король чата сегодня — {mention}!\n\n"
        f"{random.choice(_CROWN_MESSAGES)}\n\n"
        f"Трон ваш до завтра, {mention}!\n"
        f"Доступные королевские команды:\n"
        f"• /kfine @user [причина] — оштрафовать\n"
        f"• /kpardon @user — помиловать\n"
        f"• /kdecree <текст> — издать королевский указ"
    )
    await update.message.reply_text(text)


async def _require_king(update: Update) -> str | None:
    """
    Проверяет, является ли пользователь сегодняшним королём.
    Возвращает упоминание короля или None (и отвечает с ошибкой).
    """
    king = get_king_today(update.effective_chat.id)
    if not king or king["user_id"] != update.effective_user.id:
        await update.message.reply_text("👑 Только сегодняшний король может использовать эту команду!")
        return None
    return _king_mention(king)


async def kfine_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/kfine @user [причина] — Король штрафует пользователя."""
    king_mention = await _require_king(update)
    if king_mention is None:
        return

    if not context.args:
        await update.message.reply_text("Укажи кого штрафовать: /kfine @user [причина]")
        return

    target = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "нарушение королевского покоя"
    text = random.choice(_FINE_TEMPLATES).format(king=king_mention, user=target, reason=reason)
    await update.message.reply_text(text)


async def kpardon_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/kpardon @user — Король милует пользователя."""
    king_mention = await _require_king(update)
    if king_mention is None:
        return

    if not context.args:
        await update.message.reply_text("Укажи кого миловать: /kpardon @user")
        return

    target = context.args[0]
    text = random.choice(_PARDON_TEMPLATES).format(king=king_mention, user=target)
    await update.message.reply_text(text)


async def kdecree_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/kdecree <текст> — Король издаёт указ."""
    king_mention = await _require_king(update)
    if king_mention is None:
        return

    if not context.args:
        await update.message.reply_text("Напиши текст указа: /kdecree <текст>")
        return

    decree = " ".join(context.args)
    text = (
        f"══ КОРОЛЕВСКИЙ УКАЗ ══\n\n"
        f"Я, {king_mention}, повелеваю:\n\n"
        f"«{decree}»\n\n"
        f"Подписано и скреплено королевской печатью 👑"
    )
    await update.message.reply_text(text)


async def kreward_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/kreward @user — Король награждает подданного."""
    king_mention = await _require_king(update)
    if king_mention is None:
        return

    if not context.args:
        await update.message.reply_text("Укажи кого наградить: /kreward @user")
        return

    target = context.args[0]
    text = random.choice(_REWARD_TEMPLATES).format(king=king_mention, user=target)
    await update.message.reply_text(text)


async def ktax_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ktax — Король вводит налог для всего чата."""
    king_mention = await _require_king(update)
    if king_mention is None:
        return

    text = random.choice(_TAX_TEMPLATES).format(king=king_mention)
    await update.message.reply_text(text)
