# ==============================================================================
# database.py — Работа с SQLite базой данных
# ==============================================================================

import datetime
import logging
import sqlite3
from config import DATABASE_PATH

_MSK = datetime.timezone(datetime.timedelta(hours=3))

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # journal_mode=WAL устанавливается один раз в init_db() и персистентна в файле БД.
    # synchronous=NORMAL нужно ставить на каждое соединение (это per-connection настройка).
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Инициализирует базу данных: создаёт таблицы, запускает миграции."""
    conn = get_connection()
    try:
        # WAL-режим делаем здесь один раз — он сохраняется в файле БД навсегда.
        conn.execute("PRAGMA journal_mode=WAL")
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

        # ── bot_messages ─────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS bot_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                preview    TEXT,
                sent_at    REAL NOT NULL DEFAULT (unixepoch())
            )
        """)
        # ── achievements ─────────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                user_id        INTEGER,
                chat_id        INTEGER,
                achievement_id TEXT,
                earned_at      TEXT,
                PRIMARY KEY (user_id, chat_id, achievement_id)
            )
        """)

        # ── activity_streaks ──────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS activity_streaks (
                user_id    INTEGER,
                chat_id    INTEGER,
                last_date  TEXT,
                streak     INTEGER DEFAULT 1,
                max_streak INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_bot_messages_chat    ON bot_messages(chat_id, sent_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_photo_ratings_key    ON photo_ratings(key)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_photo_ratings_chat   ON photo_ratings(chat_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_photo_votes_photo    ON photo_votes(photo_id)")
        # Индексы для быстрых запросов /top и /stats
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_msg       ON user_stats(chat_id, msg_count DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_swear     ON user_stats(chat_id, swear_count DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_photo_ratings_author ON photo_ratings(author_id, chat_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_photo_comments_photo ON photo_comments(photo_id)")

        conn.commit()
    finally:
        conn.close()


# ── achievements ───────────────────────────────────────────────────────────

def grant_achievement(user_id: int, chat_id: int, achievement_id: str) -> bool:
    """Выдаёт ачивку. Возвращает True если выдана впервые (не дубль)."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO achievements (user_id, chat_id, achievement_id, earned_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, achievement_id, datetime.datetime.now(_MSK).isoformat()))
        changed = conn.total_changes
        conn.commit()
        return changed > 0
    finally:
        conn.close()


def get_user_achievements(user_id: int, chat_id: int) -> list:
    """Возвращает список ачивок пользователя [(achievement_id, earned_at), ...]."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT achievement_id, earned_at FROM achievements "
            "WHERE user_id=? AND chat_id=? ORDER BY earned_at",
            (user_id, chat_id)
        ).fetchall()
    finally:
        conn.close()


# ── activity_streaks ───────────────────────────────────────────────────────

def update_streak(user_id: int, chat_id: int) -> tuple[int, bool]:
    """
    Обновляет стрик активности. Возвращает (текущий_стрик, is_new_day).
    is_new_day=True только если это первое сообщение за сегодня.
    """
    today = datetime.datetime.now(_MSK).date().isoformat()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT last_date, streak, max_streak FROM activity_streaks "
            "WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO activity_streaks (user_id, chat_id, last_date, streak, max_streak) "
                "VALUES (?, ?, ?, 1, 1)",
                (user_id, chat_id, today)
            )
            conn.commit()
            return 1, True

        rd = dict(row)
        if rd["last_date"] == today:
            return rd["streak"], False  # уже обновляли сегодня

        last_d  = datetime.date.fromisoformat(rd["last_date"])
        today_d = datetime.date.fromisoformat(today)
        diff    = (today_d - last_d).days

        new_streak = rd["streak"] + 1 if diff == 1 else 1
        new_max    = max(rd["max_streak"], new_streak)
        conn.execute(
            "UPDATE activity_streaks SET last_date=?, streak=?, max_streak=? "
            "WHERE user_id=? AND chat_id=?",
            (today, new_streak, new_max, user_id, chat_id)
        )
        conn.commit()
        return new_streak, True
    finally:
        conn.close()


def get_streak(user_id: int, chat_id: int) -> tuple[int, int]:
    """Возвращает (current_streak, max_streak)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT streak, max_streak FROM activity_streaks WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        ).fetchone()
        if not row:
            return 0, 0
        return row["streak"], row["max_streak"]
    finally:
        conn.close()


def get_top_streaks(chat_id: int, limit: int = 5) -> list:
    """Топ участников по текущему стрику."""
    conn = get_connection()
    try:
        return conn.execute("""
            SELECT s.user_id, s.streak, s.max_streak,
                   u.first_name, u.username
            FROM activity_streaks s
            LEFT JOIN user_stats u ON s.user_id = u.user_id AND s.chat_id = u.chat_id
            WHERE s.chat_id = ?
            ORDER BY s.streak DESC LIMIT ?
        """, (chat_id, limit)).fetchall()
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
    today = datetime.datetime.now(_MSK).date().isoformat()  # дата в МСК, не UTC
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



# ── king_of_day ────────────────────────────────────────────────────────────

def get_king_today(chat_id: int):
    """Возвращает сегодняшнего короля чата или None."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM king_of_day WHERE chat_id = ? AND date = ?",
            (chat_id, datetime.datetime.now(_MSK).date().isoformat())
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
        """, (chat_id, datetime.datetime.now(_MSK).date().isoformat(), user_id, username, first_name))
        conn.commit()
    finally:
        conn.close()


def get_chat_message_count(chat_id: int) -> int:
    """Возвращает суммарное количество сообщений в чате (всё время)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT SUM(msg_count) AS total FROM user_stats WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        return int(dict(row).get("total") or 0)
    finally:
        conn.close()


def get_chat_user_count(chat_id: int) -> int:
    """Возвращает количество уникальных пользователей в чате (в базе)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM user_stats WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        return int(dict(row).get("cnt") or 0)
    finally:
        conn.close()


def get_today_swear_count(chat_id: int) -> int:
    """Возвращает суммарное количество матов за сегодня (МСК)."""
    today = datetime.datetime.now(_MSK).date().isoformat()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT SUM(swear_count) AS total FROM daily_swears WHERE chat_id = ? AND date = ?",
            (chat_id, today)
        ).fetchone()
        return int(dict(row).get("total") or 0)
    finally:
        conn.close()

def clear_chat_stats(chat_id: int) -> dict:
    """
    Полная очистка статистики чата.
    Удаляет: user_stats, achievements, activity_streaks, daily_swears, king_of_day.
    НЕ трогает: photo_ratings, photo_votes, photo_comments, bot_messages.
    Возвращает dict {table: rows_deleted}.
    """
    tables = ("user_stats", "achievements", "activity_streaks", "daily_swears", "king_of_day")
    conn = get_connection()
    try:
        counts = {}
        for table in tables:
            cur = conn.execute(f"DELETE FROM {table} WHERE chat_id = ?", (chat_id,))
            counts[table] = cur.rowcount
        conn.commit()
        return counts
    finally:
        conn.close()


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
            SELECT pr.key, pr.photo_id, pr.author_id, pr.author_name, pr.anonymous,
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


def delete_photo_by_key(key: str, requester_id: int) -> tuple[bool, str, str]:
    """
    Удаляет фото если requester_id == author_id.
    Возвращает (success, photo_id, media_type).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT photo_id, author_id, media_type, anonymous FROM photo_ratings WHERE key = ?", (key,)
        ).fetchone()
        if not row:
            return False, "", ""
        if row["author_id"] != requester_id:
            return False, "", ""
        photo_id = row["photo_id"]
        media_type = row["media_type"] or "photo"
        conn.execute("DELETE FROM photo_votes    WHERE photo_id = ?", (photo_id,))
        conn.execute("DELETE FROM photo_comments WHERE photo_id = ?", (photo_id,))
        conn.execute("DELETE FROM photo_ratings  WHERE photo_id = ?", (photo_id,))
        conn.commit()
        return True, photo_id, media_type
    finally:
        conn.close()


def get_best_photo_since(days: int, chat_id: int = None):
    """Возвращает лучшее фото за последние N дней (по средней оценке, мин. 1 голос)."""
    conn = get_connection()
    try:
        chat_filter = "AND pr.chat_id = ?" if chat_id is not None else ""
        params = [days]
        if chat_id is not None:
            params.append(chat_id)
        return conn.execute(f"""
            SELECT pr.*, CAST(pr.total_score AS FLOAT) / NULLIF(pr.vote_count, 0) AS avg_score
            FROM photo_ratings pr
            WHERE pr.key IS NOT NULL
              AND pr.vote_count >= 1
              AND pr.created_at >= datetime('now', '-' || ? || ' days')
              {chat_filter}
            ORDER BY avg_score DESC, pr.vote_count DESC
            LIMIT 1
        """, params).fetchone()
    finally:
        conn.close()


def track_bot_message(chat_id: int, message_id: int, preview: str = "") -> None:
    """Сохраняет ID сообщения бота для возможности последующего удаления.
    Хранит не более 50 последних сообщений на чат.
    """
    try:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO bot_messages (chat_id, message_id, preview) VALUES (?, ?, ?)",
                (chat_id, message_id, (preview or "")[:120])
            )
            # Оставляем только последние 50 сообщений для данного чата
            conn.execute("""
                DELETE FROM bot_messages
                WHERE chat_id = ? AND id NOT IN (
                    SELECT id FROM bot_messages
                    WHERE chat_id = ?
                    ORDER BY sent_at DESC, id DESC
                    LIMIT 50
                )
            """, (chat_id, chat_id))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error("track_bot_message FAILED: %s", e)


def get_recent_bot_messages(chat_id: int, offset: int = 0, limit: int = 5) -> list:
    """Возвращает последние сообщения бота в чате (newest first)."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT id, chat_id, message_id, preview, sent_at FROM bot_messages "
            "WHERE chat_id = ? ORDER BY sent_at DESC, id DESC LIMIT ? OFFSET ?",
            (chat_id, limit, offset)
        ).fetchall()
    finally:
        conn.close()


def get_bot_message_count(chat_id: int) -> int:
    """Возвращает количество сохранённых сообщений бота в чате."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM bot_messages WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def get_all_bot_messages_recent(offset: int = 0, limit: int = 5) -> list:
    """Возвращает последние сообщения бота из всех чатов (newest first)."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT id, chat_id, message_id, preview, sent_at FROM bot_messages "
            "ORDER BY sent_at DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
    finally:
        conn.close()


def get_all_bot_messages_count() -> int:
    """Возвращает общее количество сохранённых сообщений бота."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM bot_messages").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def delete_bot_message_record(chat_id: int, message_id: int) -> None:
    """Удаляет запись о сообщении из таблицы отслеживания."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM bot_messages WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_and_delete_old_photos(days: int) -> list:
    """
    Возвращает и удаляет из БД фото старше N дней.
    Возвращает список (key, media_type) для удаления с диска.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, media_type FROM photo_ratings "
            "WHERE key IS NOT NULL AND created_at IS NOT NULL "
            "AND created_at < datetime('now', '-' || ? || ' days')",
            (days,)
        ).fetchall()
        if not rows:
            return []
        keys = [r["key"] for r in rows]
        photo_ids = conn.execute(
            f"SELECT photo_id FROM photo_ratings WHERE key IN ({','.join('?' * len(keys))})",
            keys
        ).fetchall()
        ids = [r["photo_id"] for r in photo_ids]
        if ids:
            conn.execute(f"DELETE FROM photo_votes    WHERE photo_id IN ({','.join('?' * len(ids))})", ids)
            conn.execute(f"DELETE FROM photo_comments WHERE photo_id IN ({','.join('?' * len(ids))})", ids)
            conn.execute(f"DELETE FROM photo_ratings  WHERE photo_id IN ({','.join('?' * len(ids))})", ids)
        conn.commit()
        return [(r["key"], r["media_type"] or "photo") for r in rows]
    finally:
        conn.close()
