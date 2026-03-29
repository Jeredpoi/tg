# ==============================================================================
# commands/setavatar.py — /setavatar: установить аватар группы (только владелец)
# ==============================================================================

from telegram import Update
from telegram.ext import ContextTypes
from config import OWNER_ID


async def setavatar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/setavatar — ответить на фото чтобы установить его как аватар группы."""
    if update.effective_user.id != OWNER_ID:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Команда работает только в группах.")
        return

    reply = update.message.reply_to_message
    if not reply or not reply.photo:
        await update.message.reply_text(
            "📷 Ответь на фото командой /setavatar — "
            "и я установлю его как аватар группы."
        )
        return

    try:
        await update.message.delete()
    except Exception:
        pass

    photo = reply.photo[-1]  # наибольший доступный размер
    try:
        photo_file = await context.bot.get_file(photo.file_id)
        photo_bytes = await photo_file.download_as_bytearray()

        import io
        await context.bot.set_chat_photo(
            chat_id=chat.id,
            photo=io.BytesIO(bytes(photo_bytes)),
        )
        note = await context.bot.send_message(
            chat_id=chat.id,
            text="✅ Аватар группы обновлён.",
            disable_notification=True,
        )
        async def _del(ctx):
            try:
                await ctx.bot.delete_message(chat.id, note.message_id)
            except Exception:
                pass
        context.job_queue.run_once(_del, 5)
    except Exception as e:
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"❌ Не удалось установить аватар: {e}",
        )
