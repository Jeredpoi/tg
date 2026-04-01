"""Utilities for reading recent log entries."""
import os
import logging

_LOG_FILE = os.path.join(os.path.dirname(__file__), "bot.log")

def get_recent_logs(n: int = 20) -> list[str]:
    """Return last n non-empty lines from bot.log."""
    if not os.path.exists(_LOG_FILE):
        return []
    try:
        with open(_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip() for l in f if l.strip()]
        return lines[-n:]
    except OSError:
        return []
