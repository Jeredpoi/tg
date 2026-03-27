# ==============================================================================
# chat_config.py — Роли чатов (main / test)
# ==============================================================================
#
# Использование:
#   /setchat main  — назначить текущую группу основной (рассылки, /anon, /rate)
#   /setchat test  — снять метку main (группа становится тестовой)
#   /setchat       — показать текущую роль группы
# ==============================================================================

import json
import os

_ROLES_FILE = os.path.join(os.path.dirname(__file__), "chat_roles.json")


def _load() -> dict:
    try:
        with open(_ROLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    with open(_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_roles: dict = _load()


def get_main_chat_id() -> int | None:
    """Возвращает chat_id основной группы или None, если не назначена."""
    v = _roles.get("main")
    return int(v) if v is not None else None


def set_main_chat_id(chat_id: int) -> None:
    """Назначает chat_id основной группой."""
    _roles["main"] = chat_id
    _save(_roles)


def unset_main_chat(chat_id: int) -> bool:
    """Снимает метку main с chat_id. Возвращает True если она там была."""
    if _roles.get("main") == chat_id:
        del _roles["main"]
        _save(_roles)
        return True
    return False


def is_main_chat(chat_id: int) -> bool:
    """True если chat_id является основной группой."""
    main = _roles.get("main")
    return main is not None and int(main) == chat_id
