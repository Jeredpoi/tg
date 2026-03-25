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
    try:
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
        if "media_type" not in pr_cols:
            c.execute("ALTER TABLE photo_ratings ADD COLUMN media_type TEXT DEFAULT 'photo'")
        if "created_at" not in pr_cols:
            c.execute("ALTER TABLE photo_ratings ADD COLUMN created_at TEXT")

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

        # ── daily_swears ─────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_swears (
                chat_id     INTEGER,
                date        TEXT,
                user_id     INTEGER,
                first_name  TEXT,
                swear_count INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, date, user_id)
            )
        """)

        # ── photo_comments ───────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS photo_comments (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_id       TEXT NOT NULL,
                commenter_id   INTEGER,
                commenter_name TEXT NOT NULL,
                text           TEXT NOT NULL,
                created_at     TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        conn.commit()
    finally:
        conn.close()


# ── user_stats ─────────────────────────────────────────────────────────────

def track_message(user_id: int, username: str, first_name: str,
                  swear_count: int = 0, chat_id: int = 0) -> None:
    """Upsert пользователя и инкрементирует счётчики."""
    try:
        conn = get_connection()
        try:
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
        finally:
            conn.close()
    except Exception as e:
        logger.error("track_message FAILED: %s", e, exc_info=True)


def get_top_messages(chat_id: int = 0, limit: int = 10) -> list:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT first_name, username, msg_count FROM user_stats "
            "WHERE chat_id = ? ORDER BY msg_count DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
    finally:
        conn.close()


def get_top_swears(chat_id: int = 0, limit: int = 10) -> list:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT first_name, username, swear_count FROM user_stats "
            "WHERE chat_id = ? ORDER BY swear_count DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
    finally:
        conn.close()


def track_daily_swear(chat_id: int, user_id: int, first_name: str, count: int) -> None:
    """Добавляет маты пользователя в дневную статистику."""
    today = str(_date.today())
    try:
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO daily_swears (chat_id, date, user_id, first_name, swear_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, date, user_id) DO UPDATE SET
                    first_name  = excluded.first_name,
                    swear_count = swear_count + excluded.swear_count
            """, (chat_id, today, user_id, first_name, count))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error("track_daily_swear FAILED: %s", e, exc_info=True)


def get_daily_swear_report(chat_id: int, date: str) -> tuple:
    """Возвращает (total, [(first_name, count), ...]) по матам за дату."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT first_name, swear_count FROM daily_swears "
            "WHERE chat_id = ? AND date = ? ORDER BY swear_count DESC",
            (chat_id, date)
        ).fetchall()
        total = sum(r["swear_count"] for r in rows)
        return total, [(r["first_name"], r["swear_count"]) for r in rows]
    finally:
        conn.close()


def get_all_users(chat_id: int = 0) -> list:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT user_id, username, first_name FROM user_stats WHERE chat_id = ?",
            (chat_id,)
        ).fetchall()
    finally:
        conn.close()


# ── king_of_day ────────────────────────────────────────────────────────────

def get_king_today(chat_id: int):
    """Возвращает сегодняшнего короля чата или None."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM king_of_day WHERE chat_id = ? AND date = ?",
            (chat_id, str(_date.today()))
        ).fetchone()
    finally:
        conn.close()


def set_king_today(chat_id: int, user_id: int, username: str, first_name: str) -> None:
    """Записывает короля дня для чата."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO king_of_day (chat_id, date, user_id, username, first_name)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, str(_date.today()), user_id, username, first_name))
        conn.commit()
    finally:
        conn.close()


# ── photo_ratings ──────────────────────────────────────────────────────────

def save_photo(photo_id: str, message_id: int, chat_id: int,
               author_id: int, author_name: str, anonymous: bool,
               key: str = "", media_type: str = "photo") -> None:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO photo_ratings
                (photo_id, key, message_id, chat_id, author_id, author_name, anonymous, media_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(photo_id) DO UPDATE SET
                key         = excluded.key,
                message_id  = excluded.message_id,
                anonymous   = excluded.anonymous,
                media_type  = excluded.media_type
        """, (photo_id, key, message_id, chat_id, author_id, author_name, int(anonymous), media_type))
        conn.commit()
    finally:
        conn.close()


def get_photo_by_key(key: str):
    """Возвращает строку photo_ratings по короткому ключу."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM photo_ratings WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()


def close_photo(photo_id: str) -> None:
    """Помечает голосование как завершённое."""
    conn = get_connection()
    try:
        conn.execute("UPDATE photo_ratings SET closed = 1 WHERE photo_id = ?", (photo_id,))
        conn.commit()
    finally:
        conn.close()


def add_vote(photo_id: str, voter_id: int, score: int) -> tuple[float, int]:
    """Добавляет/обновляет голос. Возвращает (средняя оценка, кол-во голосов)."""
    conn = get_connection()
    try:
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

        if row and row["vote_count"] > 0:
            avg = row["total_score"] / row["vote_count"]
            return round(avg, 2), row["vote_count"]
        return 0.0, 0
    finally:
        conn.close()


def get_gallery(limit: int = 100, chat_id: int = None, sort: str = "score", exclude_anonymous: bool = False) -> list:
    """Возвращает фото с кол-вом комментариев, отсортированные по выбранному критерию."""
    order_map = {
        "votes": "pr.vote_count DESC",
        "date":  "pr.created_at DESC",
    }
    order = order_map.get(sort, "CAST(pr.total_score AS FLOAT) / NULLIF(pr.vote_count, 0) DESC, pr.vote_count DESC")

    conn = get_connection()
    try:
        chat_filter = "AND pr.chat_id = ?" if chat_id is not None else ""
        anon_filter = "AND pr.anonymous = 0" if exclude_anonymous else ""
        params = tuple(filter(lambda x: x is not None, [chat_id, limit]))
        return conn.execute(f"""
            SELECT pr.key, pr.photo_id, pr.author_name, pr.anonymous,
                   pr.total_score, pr.vote_count, pr.closed, pr.media_type, pr.created_at,
                   COUNT(pc.id) AS comment_count
            FROM photo_ratings pr
            LEFT JOIN photo_comments pc ON pc.photo_id = pr.photo_id
            WHERE pr.key IS NOT NULL {chat_filter} {anon_filter}
            GROUP BY pr.photo_id
            ORDER BY {order}
            LIMIT ?
        """, params).fetchall()
    finally:
        conn.close()


# ── photo_comments ─────────────────────────────────────────────────────────

def get_comments(photo_id: str) -> list:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT id, commenter_id, commenter_name, text, created_at FROM photo_comments "
            "WHERE photo_id = ? ORDER BY created_at ASC",
            (photo_id,)
        ).fetchall()
    finally:
        conn.close()


def add_comment(photo_id: str, commenter_id: int, commenter_name: str, text: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO photo_comments (photo_id, commenter_id, commenter_name, text) VALUES (?, ?, ?, ?)",
            (photo_id, commenter_id, commenter_name, text.strip())
        )
        conn.commit()
    finally:
        conn.close()


def get_user_stats(user_id: int, chat_id: int) -> dict:
    """Возвращает личную статистику пользователя в чате."""
    conn = get_connection()
    try:
        user_row = conn.execute(
            "SELECT msg_count, swear_count FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()

        photos = conn.execute(
            """SELECT COUNT(*) AS cnt,
                      COALESCE(SUM(total_score), 0) AS total,
                      COALESCE(SUM(vote_count), 0)  AS votes,
                      MAX(CAST(total_score AS FLOAT) / NULLIF(vote_count, 0)) AS best
               FROM photo_ratings
               WHERE author_id = ? AND chat_id = ? AND vote_count > 0 AND anonymous = 0""",
            (user_id, chat_id)
        ).fetchone()

        king_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM king_of_day WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ).fetchone()

        msg_rank = conn.execute(
            """SELECT COUNT(*) + 1 AS rank FROM user_stats
               WHERE chat_id = ? AND msg_count > (
                   SELECT COALESCE(msg_count, 0) FROM user_stats WHERE user_id = ? AND chat_id = ?
               )""",
            (chat_id, user_id, chat_id)
        ).fetchone()
    finally:
        conn.close()

    photo_cnt   = photos["cnt"]   if photos else 0
    total_votes = photos["votes"] if photos else 0
    avg_score   = round(photos["total"] / total_votes, 1) if total_votes else 0
    best_score  = round(photos["best"], 1) if photos and photos["best"] else 0

    return {
        "msg_count":   user_row["msg_count"]   if user_row else 0,
        "swear_count": user_row["swear_count"] if user_row else 0,
        "msg_rank":    msg_rank["rank"]        if msg_rank else 1,
        "king_count":  king_count["cnt"]       if king_count else 0,
        "photo_count": photo_cnt,
        "total_votes": total_votes,
        "avg_score":   avg_score,
        "best_score":  best_score,
    }


def clear_all_photos() -> None:
    """Удаляет все фото/видео рейтинги, голоса и комментарии из БД."""
    conn = get_connection()
    try:
        conn.executescript("""
            DELETE FROM photo_votes;
            DELETE FROM photo_comments;
            DELETE FROM photo_ratings;
        """)
        conn.commit()
    finally:
        conn.close()


def get_photo(photo_id: str):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM photo_ratings WHERE photo_id = ?", (photo_id,)
        ).fetchone()
    finally:
        conn.close()
