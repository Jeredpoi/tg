# ==============================================================================
# database.py — Работа с SQLite базой данных
# ==============================================================================

import logging
import sqlite3
from config import DATABASE_PATH

logger = logging.getLogger(__name__)
logger.info("DATABASE_PATH resolved to: %s", DATABASE_PATH)


def get_connection() -> sqlite3.Connection:
    """Возвращает соединение с базой данных."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Доступ к колонкам по имени
    return conn


def init_db() -> None:
    """Инициализирует базу данных: создаёт таблицы если они не существуют."""
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица статистики пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            msg_count   INTEGER DEFAULT 0,
            swear_count INTEGER DEFAULT 0
        )
    """)

    # Таблица оценок фото
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS photo_ratings (
            photo_id    TEXT PRIMARY KEY,
            message_id  INTEGER,
            chat_id     INTEGER,
            author_id   INTEGER,
            author_name TEXT,
            anonymous   INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            vote_count  INTEGER DEFAULT 0
        )
    """)

    # Таблица голосов за фото (чтобы один пользователь голосовал только раз)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS photo_votes (
            photo_id TEXT,
            voter_id INTEGER,
            score    INTEGER,
            PRIMARY KEY (photo_id, voter_id)
        )
    """)

    conn.commit()
    conn.close()


# ------------------------------------------------------------------------------
# Статистика пользователей
# ------------------------------------------------------------------------------

def upsert_user(user_id: int, username: str, first_name: str) -> None:
    """Создаёт запись пользователя или обновляет имя если уже есть."""
    logger.info("upsert_user called: user_id=%s, username=%s, first_name=%s", user_id, username, first_name)
    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO user_stats (user_id, username, first_name, msg_count, swear_count)
            VALUES (?, ?, ?, 0, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        conn.commit()
        conn.close()
        logger.info("upsert_user OK")
    except Exception as e:
        logger.error("upsert_user FAILED: %s", e, exc_info=True)


def increment_message(user_id: int) -> None:
    """Увеличивает счётчик сообщений пользователя на 1."""
    conn = get_connection()
    conn.execute(
        "UPDATE user_stats SET msg_count = msg_count + 1 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def increment_swear(user_id: int, count: int = 1) -> None:
    """Увеличивает счётчик матов пользователя."""
    conn = get_connection()
    conn.execute(
        "UPDATE user_stats SET swear_count = swear_count + ? WHERE user_id = ?",
        (count, user_id)
    )
    conn.commit()
    conn.close()


def get_top_messages(limit: int = 10) -> list:
    """Возвращает топ пользователей по количеству сообщений."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT first_name, username, msg_count FROM user_stats ORDER BY msg_count DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return rows


def get_top_swears(limit: int = 10) -> list:
    """Возвращает топ пользователей по количеству матов."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT first_name, username, swear_count FROM user_stats ORDER BY swear_count DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return rows


def get_all_users() -> list:
    """Возвращает всех пользователей из базы."""
    conn = get_connection()
    rows = conn.execute("SELECT user_id, username, first_name FROM user_stats").fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------------------------
# Оценки фото
# ------------------------------------------------------------------------------

def save_photo(photo_id: str, message_id: int, chat_id: int,
               author_id: int, author_name: str, anonymous: bool) -> None:
    """Сохраняет информацию о фото для оценки."""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO photo_ratings
            (photo_id, message_id, chat_id, author_id, author_name, anonymous)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (photo_id, message_id, chat_id, author_id, author_name, int(anonymous)))
    conn.commit()
    conn.close()


def add_vote(photo_id: str, voter_id: int, score: int) -> tuple[float, int]:
    """
    Добавляет или обновляет голос пользователя за фото.
    Возвращает (средняя оценка, количество голосов).
    """
    conn = get_connection()

    # Проверяем, голосовал ли уже пользователь
    existing = conn.execute(
        "SELECT score FROM photo_votes WHERE photo_id = ? AND voter_id = ?",
        (photo_id, voter_id)
    ).fetchone()

    if existing:
        old_score = existing["score"]
        # Обновляем голос
        conn.execute(
            "UPDATE photo_votes SET score = ? WHERE photo_id = ? AND voter_id = ?",
            (score, photo_id, voter_id)
        )
        conn.execute("""
            UPDATE photo_ratings
            SET total_score = total_score - ? + ?
            WHERE photo_id = ?
        """, (old_score, score, photo_id))
    else:
        # Новый голос
        conn.execute(
            "INSERT INTO photo_votes (photo_id, voter_id, score) VALUES (?, ?, ?)",
            (photo_id, voter_id, score)
        )
        conn.execute("""
            UPDATE photo_ratings
            SET total_score = total_score + ?,
                vote_count  = vote_count + 1
            WHERE photo_id = ?
        """, (score, photo_id))

    conn.commit()

    # Получаем обновлённую статистику
    row = conn.execute(
        "SELECT total_score, vote_count FROM photo_ratings WHERE photo_id = ?",
        (photo_id,)
    ).fetchone()
    conn.close()

    if row and row["vote_count"] > 0:
        avg = row["total_score"] / row["vote_count"]
        return round(avg, 2), row["vote_count"]
    return 0.0, 0


def get_photo(photo_id: str) -> sqlite3.Row | None:
    """Возвращает данные фото по его ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM photo_ratings WHERE photo_id = ?", (photo_id,)
    ).fetchone()
    conn.close()
    return row
