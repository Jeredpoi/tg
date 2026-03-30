# ==============================================================================
# commands/restart.py — /restart: перезапустить бота (только владелец)
# ==============================================================================

import asyncio
import json
import os
import sys
from telegram import Update
from telegram.ext import ContextTypes
from config import OWNER_ID

_RESTART_STATE_FILE = "/tmp/tg_restart_state.json"


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/restart — мягкий перезапуск бота (только владелец, только PM)."""
    if update.effective_user.id != OWNER_ID:
        return

    if update.effective_chat.type != "private":
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    note = await update.message.reply_text(
        "🔄 <b>Перезапускаю бота...</b>\n\n"
        "<i>Бот будет недоступен несколько секунд.</i>",
        parse_mode="HTML",
    )

    # Сохраняем состояние для уведомления после перезапуска
    try:
        with open(_RESTART_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "chat_id":  update.effective_chat.id,
                "cmd_mid":  update.message.message_id,
                "note_mid": note.message_id,
            }, f)
    except Exception as e:
        await note.edit_text(f"❌ Не удалось сохранить состояние: {e}\nПерезапуск отменён.")
        return

    await asyncio.sleep(0.5)
    os.execl(sys.executable, sys.executable, *sys.argv)


async def send_restart_done(app) -> None:
    """Вызывается при старте бота: если есть файл состояния — шлём уведомление."""
    if not os.path.exists(_RESTART_STATE_FILE):
        return
    try:
        with open(_RESTART_STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        os.remove(_RESTART_STATE_FILE)
    except Exception:
        return

    chat_id  = state.get("chat_id")
    cmd_mid  = state.get("cmd_mid")
    note_mid = state.get("note_mid")

    if not chat_id:
        return

    try:
        done_msg = await app.bot.send_message(
            chat_id=chat_id,
            text="✅ <b>Перезагрузка завершена.</b>",
            parse_mode="HTML",
        )
    except Exception:
        return

    # Удаляем /restart команду, старое "перезапускаю" сообщение и уведомление через 20 сек
    async def _cleanup(ctx):
        for mid in [cmd_mid, note_mid, done_msg.message_id]:
            if mid:
                try:
                    await ctx.bot.delete_message(chat_id, mid)
                except Exception:
                    pass

    if app.job_queue:
        app.job_queue.run_once(_cleanup, 20)
