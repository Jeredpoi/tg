# ==============================================================================
# chat_config.py — Роли чатов и список инициализированных групп
# ==============================================================================

import json
import os

_ROLES_FILE = os.path.join(os.path.dirname(__file__), "chat_roles.json")
_SETUP_FILE = os.path.join(os.path.dirname(__file__), "setup_chats.json")


# ── Роли (main / test) ────────────────────────────────────────────────────────

def _load_roles() -> dict:
    try:
        with open(_ROLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_roles(data: dict) -> None:
    with open(_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_roles: dict = _load_roles()


def get_main_chat_id() -> int | None:
    """Возвращает chat_id основной группы или None, если не назначена."""
    v = _roles.get("main")
    return int(v) if v is not None else None


def set_main_chat_id(chat_id: int) -> None:
    """Назначает chat_id основной группой."""
    _roles["main"] = chat_id
    _save_roles(_roles)


def unset_main_chat(chat_id: int) -> bool:
    """Снимает метку main с chat_id. Возвращает True если она там была."""
    if _roles.get("main") == chat_id:
        del _roles["main"]
        _save_roles(_roles)
        return True
    return False


def is_main_chat(chat_id: int) -> bool:
    """True если chat_id является основной группой."""
    main = _roles.get("main")
    return main is not None and int(main) == chat_id


# ── Инициализированные чаты (setup_chats) ─────────────────────────────────────

_setup_chats_cache: set[int] | None = None


def _load_setup_chats() -> set[int]:
    try:
        with open(_SETUP_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def _save_setup_chats_to_disk(chats: set[int]) -> None:
    with open(_SETUP_FILE, "w", encoding="utf-8") as f:
        json.dump(list(chats), f, ensure_ascii=False, indent=2)


def get_setup_chats() -> set[int]:
    """Возвращает множество chat_id инициализированных групп."""
    global _setup_chats_cache
    if _setup_chats_cache is None:
        _setup_chats_cache = _load_setup_chats()
    return _setup_chats_cache


def add_setup_chat(chat_id: int) -> None:
    """Добавляет чат в список инициализированных."""
    chats = get_setup_chats()
    chats.add(chat_id)
    _save_setup_chats_to_disk(chats)


def is_setup_chat(chat_id: int) -> bool:
    """True если чат уже инициализирован."""
    return chat_id in get_setup_chats()


# ── Настройки бота (bot_settings.json) ───────────────────────────────────────

_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "bot_settings.json")

# Дефолтные значения
_DEFAULT_SETTINGS = {
    "swear_detect": True,          # Реагировать на маты
    "swear_response_chance": 0.45, # Шанс ответа на мат (0.0–1.0)
    "midnight_report": True,       # Ночной отчёт по матам
    "weekly_best_photo": True,     # Еженедельное лучшее фото
    "vote_duration": 30,           # Длительность голосования (минуты)
    "cmd_cooldown": 10,            # Кулдаун команд (секунды)
    "autodel_help": 25,            # Автоудаление ответа /help (сек, 0 = выкл)
    "autodel_gallery": 25,         # Автоудаление ссылки галереи (сек, 0 = выкл)
    "autodel_ownerhelp": 20,       # Автоудаление ответа /ownerhelp (сек, 0 = выкл)
}

_settings_cache: dict | None = None


def _load_settings() -> dict:
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        # Мержим с дефолтами — на случай новых ключей
        merged = dict(_DEFAULT_SETTINGS)
        merged.update(stored)
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULT_SETTINGS)


def _save_settings(data: dict) -> None:
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_settings() -> dict:
    """Возвращает все настройки бота."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = _load_settings()
    return _settings_cache


def get_setting(key: str):
    """Возвращает значение настройки по ключу."""
    return get_settings().get(key, _DEFAULT_SETTINGS.get(key))


def set_setting(key: str, value) -> None:
    """Устанавливает значение настройки."""
    settings = get_settings()
    settings[key] = value
    _save_settings(settings)


def get_default_settings() -> dict:
    """Возвращает словарь дефолтных значений."""
    return dict(_DEFAULT_SETTINGS)


# ── Управление командами ──────────────────────────────────────────────────────

# Команды, которые можно включать/выключать через /settings
MANAGEABLE_COMMANDS = {
    "/mge":     "Фраза из МГЕ",
    "/dice":    "Бросить кубик",
    "/roast":   "Подколоть участника",
    "/top":     "Топ участников",
    "/stats":   "Статистика участника",
    "/weather": "Погода",
    "/anon":    "Анонимное голосование",
    "/rate":    "Оценить фото/видео",
    "/gallery": "Галерея фото",
    "/help":    "Помощь по командам",
}


def get_disabled_commands() -> set[str]:
    """Возвращает множество отключённых команд (напр. {'/mge', '/dice'})."""
    raw = get_settings().get("disabled_commands", [])
    return set(raw)


def disable_command(cmd: str) -> None:
    """Отключает команду."""
    disabled = get_disabled_commands()
    disabled.add(cmd)
    settings = get_settings()
    settings["disabled_commands"] = list(disabled)
    _save_settings(settings)


def enable_command(cmd: str) -> None:
    """Включает команду."""
    disabled = get_disabled_commands()
    disabled.discard(cmd)
    settings = get_settings()
    settings["disabled_commands"] = list(disabled)
    _save_settings(settings)


def is_command_enabled(cmd: str) -> bool:
    """True если команда не отключена."""
    return cmd not in get_disabled_commands()


# ── Кастомные MGE-фразы ───────────────────────────────────────────────────────

_CUSTOM_PHRASES_FILE = os.path.join(os.path.dirname(__file__), "custom_mge.json")

# Персонажи доступные для выбора
MGE_CHARACTERS = ["Скаут", "Солдат", "Снайпер", "Медик", "Пулемётчик", "Шпион", "Игрок"]


def get_custom_mge_phrases() -> list[dict]:
    """Возвращает список кастомных фраз: [{'char': '...', 'phrase': '...'}]."""
    try:
        with open(_CUSTOM_PHRASES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def add_custom_mge_phrase(char: str, phrase: str) -> None:
    """Добавляет кастомную фразу."""
    phrases = get_custom_mge_phrases()
    phrases.append({"char": char, "phrase": phrase})
    with open(_CUSTOM_PHRASES_FILE, "w", encoding="utf-8") as f:
        json.dump(phrases, f, ensure_ascii=False, indent=2)


def delete_custom_mge_phrase(idx: int) -> bool:
    """Удаляет фразу по индексу. Возвращает True если успешно."""
    phrases = get_custom_mge_phrases()
    if 0 <= idx < len(phrases):
        phrases.pop(idx)
        with open(_CUSTOM_PHRASES_FILE, "w", encoding="utf-8") as f:
            json.dump(phrases, f, ensure_ascii=False, indent=2)
        return True
    return False


# ── Кастомные ответы на маты ─────────────────────────────────────────────────

_CUSTOM_SWEAR_FILE = os.path.join(os.path.dirname(__file__), "custom_swear.json")


def get_custom_swear_responses() -> list[str]:
    """Возвращает список кастомных ответов на маты."""
    try:
        with open(_CUSTOM_SWEAR_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def add_custom_swear_response(text: str) -> None:
    """Добавляет кастомный ответ на мат."""
    responses = get_custom_swear_responses()
    responses.append(text)
    with open(_CUSTOM_SWEAR_FILE, "w", encoding="utf-8") as f:
        json.dump(responses, f, ensure_ascii=False, indent=2)


def delete_custom_swear_response(idx: int) -> bool:
    """Удаляет ответ по индексу. Возвращает True если успешно."""
    responses = get_custom_swear_responses()
    if 0 <= idx < len(responses):
        responses.pop(idx)
        with open(_CUSTOM_SWEAR_FILE, "w", encoding="utf-8") as f:
            json.dump(responses, f, ensure_ascii=False, indent=2)
        return True
    return False


_CUSTOM_TRIGGERS_FILE = os.path.join(os.path.dirname(__file__), "custom_triggers.json")


def get_custom_swear_triggers() -> list[dict]:
    """Возвращает список триггерных слов: [{word, response|None}]."""
    try:
        with open(_CUSTOM_TRIGGERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def add_custom_swear_trigger(word: str, response: str | None) -> None:
    """Добавляет триггерное слово (с опциональным ответом)."""
    triggers = get_custom_swear_triggers()
    triggers.append({"word": word.lower().strip(), "response": response})
    with open(_CUSTOM_TRIGGERS_FILE, "w", encoding="utf-8") as f:
        json.dump(triggers, f, ensure_ascii=False, indent=2)


def delete_custom_swear_trigger(idx: int) -> bool:
    """Удаляет триггер по индексу. Возвращает True если успешно."""
    triggers = get_custom_swear_triggers()
    if 0 <= idx < len(triggers):
        triggers.pop(idx)
        with open(_CUSTOM_TRIGGERS_FILE, "w", encoding="utf-8") as f:
            json.dump(triggers, f, ensure_ascii=False, indent=2)
        return True
    return False

