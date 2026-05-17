import sqlite3
from typing import Optional


class Database:
    def __init__(self, path: str):
        self.path = path

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    name        TEXT NOT NULL,
                    age         INTEGER NOT NULL,
                    gender      TEXT NOT NULL,
                    looking_for TEXT NOT NULL,
                    city        TEXT NOT NULL,
                    goal        TEXT NOT NULL,
                    bio         TEXT,
                    photo_id    TEXT,
                    is_paused   INTEGER DEFAULT 0,
                    age_min     INTEGER DEFAULT 18,
                    age_max     INTEGER DEFAULT 99,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS likes (
                    from_id   INTEGER,
                    to_id     INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (from_id, to_id)
                );

                CREATE TABLE IF NOT EXISTS skips (
                    from_id   INTEGER,
                    to_id     INTEGER,
                    PRIMARY KEY (from_id, to_id)
                );

                CREATE TABLE IF NOT EXISTS shown (
                    user_id     INTEGER PRIMARY KEY,
                    last_shown  INTEGER
                );
            """)
            # Migration: add age_min/age_max if upgrading from old schema
            cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
            if "age_min" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN age_min INTEGER DEFAULT 18")
            if "age_max" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN age_max INTEGER DEFAULT 99")

    # ── Users ──────────────────────────────────────────────────────────────

    def create_user(self, user_id, name, age, gender, looking_for,
                    city, goal, bio=None, photo_id=None, username=None,
                    age_min=18, age_max=99):
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO users
                  (user_id, username, name, age, gender, looking_for, city, goal, bio, photo_id, age_min, age_max)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, username, name, age, gender, looking_for, city, goal, bio, photo_id, age_min, age_max))

    def get_user(self, user_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_user(self, user_id: int, **kwargs):
        if not kwargs:
            return
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [user_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE users SET {fields} WHERE user_id = ?", values)

    # ── Matching logic ─────────────────────────────────────────────────────

    def get_next_candidate(self, user_id: int) -> Optional[dict]:
        """
        Find next profile matching:
        - Same city
        - Gender matches what user is looking for
        - User matches what candidate is looking for
        - Not already liked/skipped
        - Not paused
        - Not the user themselves
        """
        me = self.get_user(user_id)
        if not me:
            return None

        with self._conn() as conn:
            row = conn.execute("""
                SELECT u.* FROM users u
                WHERE u.user_id != ?
                  AND u.is_paused = 0
                  AND LOWER(u.city) = LOWER(?)
                  AND (? = 'any' OR u.gender = ?)
                  AND (u.looking_for = 'any' OR u.looking_for = ?)
                  AND u.age >= ? AND u.age <= ?
                  AND (? IS NULL OR ? BETWEEN u.age_min AND u.age_max)
                  AND u.user_id NOT IN (
                      SELECT to_id FROM likes WHERE from_id = ?
                  )
                  AND u.user_id NOT IN (
                      SELECT to_id FROM skips WHERE from_id = ?
                  )
                ORDER BY RANDOM()
                LIMIT 1
            """, (
                user_id,
                me["city"],
                me["looking_for"], me["looking_for"],
                me["gender"],
                me.get("age_min", 18), me.get("age_max", 99),
                me["age"], me["age"],
                user_id,
                user_id,
            )).fetchone()

        if not row:
            return None

        candidate = dict(row)
        # Track last shown
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO shown (user_id, last_shown) VALUES (?, ?)
            """, (user_id, candidate["user_id"]))

        return candidate

    def get_last_shown(self, user_id: int) -> Optional[int]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT last_shown FROM shown WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row["last_shown"] if row else None

    # ── Likes / Skips ──────────────────────────────────────────────────────

    def add_like(self, from_id: int, to_id: int):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO likes (from_id, to_id) VALUES (?, ?)",
                (from_id, to_id)
            )

    def add_skip(self, from_id: int, to_id: int):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO skips (from_id, to_id) VALUES (?, ?)",
                (from_id, to_id)
            )

    def is_mutual_like(self, user_id: int, target_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT 1 FROM likes
                WHERE from_id = ? AND to_id = ?
            """, (target_id, user_id)).fetchone()
        return row is not None
