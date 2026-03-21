# ==============================================================================
# database.py — Работа с SQLite базой данных
# ==============================================================================

import logging
import sqlite3
from datetime import date as _date
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Инициализирует базу данных: создаёт таблицы, запускает миграции."""
    conn = get_connection()
    c = conn.cursor()

    # ── user_stats ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id     INTEGER,
            chat_id     INTEGER NOT NULL DEFAULT 0,
            username    TEXT,
            first_name  TEXT,
            msg_count   INTEGER DEFAULT 0,
            swear_count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        )
    """)

    # Миграция: старая таблица без chat_id (PK = user_id)
    cols = {row[1] for row in c.execute("PRAGMA table_info(user_stats)")}
    if "chat_id" not in cols:
        conn.executescript("""
            ALTER TABLE user_stats RENAME TO _us_old;
            CREATE TABLE user_stats (
                user_id     INTEGER,
                chat_id     INTEGER NOT NULL DEFAULT 0,
                username    TEXT,
                first_name  TEXT,
                msg_count   INTEGER DEFAULT 0,
                swear_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            );
            INSERT INTO user_stats
                SELECT user_id, 0, username, first_name, msg_count, swear_count
                FROM _us_old;
            DROP TABLE _us_old;
        """)

    # ── photo_ratings ───────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS photo_ratings (
            photo_id    TEXT PRIMARY KEY,
            key         TEXT,
            message_id  INTEGER,
            chat_id     INTEGER,
            author_id   INTEGER,
            author_name TEXT,
            anonymous   INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            vote_count  INTEGER DEFAULT 0,
            closed      INTEGER DEFAULT 0
        )
    """)
    pr_cols = {row[1] for row in c.execute("PRAGMA table_info(photo_ratings)")}
    if "closed" not in pr_cols:
        c.execute("ALTER TABLE photo_ratings ADD COLUMN closed INTEGER DEFAULT 0")
    if "key" not in pr_cols:
        c.execute("ALTER TABLE photo_ratings ADD COLUMN key TEXT")

    # ── photo_votes ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS photo_votes (
            photo_id TEXT,
            voter_id INTEGER,
            score    INTEGER,
            PRIMARY KEY (photo_id, voter_id)
        )
    """)

    # ── king_of_day ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS king_of_day (
            chat_id    INTEGER,
            date       TEXT,
            user_id    INTEGER,
            username   TEXT,
            first_name TEXT,
            PRIMARY KEY (chat_id, date)
        )
    """)

    conn.commit()
    conn.close()


# ── user_stats ─────────────────────────────────────────────────────────────

def track_message(user_id: int, username: str, first_name: str,
                  swear_count: int = 0, chat_id: int = 0) -> None:
    """Upsert пользователя и инкрементирует счётчики."""
    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO user_stats (user_id, chat_id, username, first_name, msg_count, swear_count)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                username    = excluded.username,
                first_name  = excluded.first_name,
                msg_count   = msg_count + 1,
                swear_count = swear_count + excluded.swear_count
        """, (user_id, chat_id, username, first_name, swear_count))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("track_message FAILED: %s", e, exc_info=True)


def get_top_messages(chat_id: int = 0, limit: int = 10) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT first_name, username, msg_count FROM user_stats "
        "WHERE chat_id = ? ORDER BY msg_count DESC LIMIT ?",
        (chat_id, limit)
    ).fetchall()
    conn.close()
    return rows


def get_top_swears(chat_id: int = 0, limit: int = 10) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT first_name, username, swear_count FROM user_stats "
        "WHERE chat_id = ? ORDER BY swear_count DESC LIMIT ?",
        (chat_id, limit)
    ).fetchall()
    conn.close()
    return rows


def get_all_users(chat_id: int = 0) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT user_id, username, first_name FROM user_stats WHERE chat_id = ?",
        (chat_id,)
    ).fetchall()
    conn.close()
    return rows


# ── king_of_day ────────────────────────────────────────────────────────────

def get_king_today(chat_id: int):
    """Возвращает сегодняшнего короля чата или None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM king_of_day WHERE chat_id = ? AND date = ?",
        (chat_id, str(_date.today()))
    ).fetchone()
    conn.close()
    return row


def set_king_today(chat_id: int, user_id: int, username: str, first_name: str) -> None:
    """Записывает короля дня для чата."""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO king_of_day (chat_id, date, user_id, username, first_name)
        VALUES (?, ?, ?, ?, ?)
    """, (chat_id, str(_date.today()), user_id, username, first_name))
    conn.commit()
    conn.close()


# ── photo_ratings ──────────────────────────────────────────────────────────

def save_photo(photo_id: str, message_id: int, chat_id: int,
               author_id: int, author_name: str, anonymous: bool,
               key: str = "") -> None:
    conn = get_connection()
    conn.execute("""
        INSERT INTO photo_ratings
            (photo_id, key, message_id, chat_id, author_id, author_name, anonymous)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(photo_id) DO UPDATE SET
            key         = excluded.key,
            message_id  = excluded.message_id,
            anonymous   = excluded.anonymous
    """, (photo_id, key, message_id, chat_id, author_id, author_name, int(anonymous)))
    conn.commit()
    conn.close()


def get_photo_by_key(key: str):
    """Возвращает строку photo_ratings по короткому ключу."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM photo_ratings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row


def close_photo(photo_id: str) -> None:
    """Помечает голосование как завершённое."""
    conn = get_connection()
    conn.execute("UPDATE photo_ratings SET closed = 1 WHERE photo_id = ?", (photo_id,))
    conn.commit()
    conn.close()


def add_vote(photo_id: str, voter_id: int, score: int) -> tuple[float, int]:
    """Добавляет/обновляет голос. Возвращает (средняя оценка, кол-во голосов)."""
    conn = get_connection()

    existing = conn.execute(
        "SELECT score FROM photo_votes WHERE photo_id = ? AND voter_id = ?",
        (photo_id, voter_id)
    ).fetchone()

    if existing:
        old_score = existing["score"]
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

    row = conn.execute(
        "SELECT total_score, vote_count FROM photo_ratings WHERE photo_id = ?",
        (photo_id,)
    ).fetchone()
    conn.close()

    if row and row["vote_count"] > 0:
        avg = row["total_score"] / row["vote_count"]
        return round(avg, 2), row["vote_count"]
    return 0.0, 0


def get_gallery(limit: int = 100) -> list:
    """Возвращает фото отсортированные по среднему рейтингу."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT key, photo_id, author_name, anonymous, total_score, vote_count
        FROM photo_ratings
        WHERE vote_count > 0 AND key IS NOT NULL
        ORDER BY CAST(total_score AS FLOAT) / vote_count DESC,
                 vote_count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


def get_photo(photo_id: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM photo_ratings WHERE photo_id = ?", (photo_id,)
    ).fetchone()
    conn.close()
    return row
