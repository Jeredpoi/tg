import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from chat_config import (
    get_main_chat_id, set_main_chat_id, unset_main_chat, is_main_chat,
    get_monitor_chat_id, set_monitor_chat_id, unset_monitor_chat, is_monitor_chat,
    get_setup_chats, get_settings, get_setting, set_setting,
    MANAGEABLE_COMMANDS, get_disabled_commands, disable_command, enable_command,
    is_command_enabled, sync_bot_commands,
    MGE_CHARACTERS,
    get_custom_mge_phrases, add_custom_mge_phrase, delete_custom_mge_phrase,
    get_custom_swear_responses, add_custom_swear_response, delete_custom_swear_response,
    get_custom_swear_triggers, add_custom_swear_trigger, delete_custom_swear_trigger,
)
from config import OWNER_ID

logger = logging.getLogger(__name__)

# ── Состояния диалога ввода ───────────────────────────────────────────────────
# Хранятся в context.user_data["stg_state"]
STATE_AWAIT_MGE_PHRASE   = "await_mge_phrase"    # ждём текст фразы
STATE_AWAIT_SWEAR_RESP   = "await_swear_resp"    # ждём текст ответа на мат
STATE_AWAIT_TRIGGER_WORD = "await_trigger_word"  # ждём слово-триггер
STATE_AWAIT_TRIGGER_RESP = "await_trigger_resp"  # ждём ответ на триггер


def _back_to_menu_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ Главное меню", callback_data="stg:menu")


def _back_to_chats_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ К списку чатов", callback_data="stg:chats")
