# ==============================================================================
# commands/utils.py — общие утилиты для команд
# ==============================================================================

from chat_config import get_setting


async def autodel(context, setting_key: str, chat_id: int, *message_ids: int) -> None:
    """Планирует удаление сообщений через N секунд из настройки setting_key.
    Если настройка = 0 — ничего не делает.
    """
    delay = get_setting(setting_key)
    if not delay:
        return
    mids = [m for m in message_ids if m]

    async def _delete(ctx):
        for mid in mids:
            try:
                await ctx.bot.delete_message(chat_id, mid)
            except Exception:
                pass

    context.job_queue.run_once(_delete, delay)
