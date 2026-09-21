"""Database layer: SQLite connection management, schema, and query helpers."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    password_salt TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    category     TEXT    NOT NULL CHECK (length(category) BETWEEN 1 AND 50),
    note         TEXT    NOT NULL DEFAULT '' CHECK (length(note) <= 500),
    date         TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_expenses_date     ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
"""


class Database:
    """Thin wrapper around a sqlite3 connection with a single shared
    connection (avoids the ':memory:' per-connection gotcha) and a lock."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            columns = {
                row[1] for row in self._conn.execute("PRAGMA table_info(expenses)")
            }
            if "user_id" not in columns:
                # Upgrade databases created before JWT support. Existing rows
                # stay in the legacy shared namespace (user_id NULL).
                self._conn.execute(
                    "ALTER TABLE expenses ADD COLUMN user_id INTEGER REFERENCES users(id)"
                )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_expenses_user_date "
                "ON expenses(user_id, date)"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _rows(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    # ---- writes ----

    def create_user(
        self, username: str, password_hash: str, password_salt: str
    ) -> sqlite3.Row:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO users (username, password_hash, password_salt) "
                "VALUES (?, ?, ?)",
                (username, password_hash, password_salt),
            )
            self._conn.commit()
            return self._conn.execute(
                "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
            ).fetchone()

    def get_user_by_username(self, username: str) -> sqlite3.Row | None:
        return self._one("SELECT * FROM users WHERE username = ?", (username,))

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        return self._one("SELECT * FROM users WHERE id = ?", (user_id,))

    def create_expense(
        self,
        amount_cents: int,
        category: str,
        note: str,
        date: str,
        user_id: int | None = None,
    ) -> sqlite3.Row:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO expenses (user_id, amount_cents, category, note, date)"
                " VALUES (?, ?, ?, ?, ?)",
                (user_id, amount_cents, category, note, date),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return row

    # ---- reads ----

    def list_expenses(
        self,
        category: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        user_id: int | None = None,
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM expenses"
        clauses: list[str] = []
        params: list[Any] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if category is not None:
            clauses.append("LOWER(category) = LOWER(?)")
            params.append(category)
        if start_date is not None:
            clauses.append("date >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("date <= ?")
            params.append(end_date)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY date DESC, id DESC"
        return self._rows(sql, params)

    def total_all(self, user_id: int | None = None) -> int:
        sql = "SELECT COALESCE(SUM(amount_cents), 0) AS t FROM expenses"
        params: tuple[Any, ...] = ()
        if user_id is not None:
            sql += " WHERE user_id = ?"
            params = (user_id,)
        row = self._one(sql, params)
        return int(row["t"])

    def count_all(self, user_id: int | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM expenses"
        params: tuple[Any, ...] = ()
        if user_id is not None:
            sql += " WHERE user_id = ?"
            params = (user_id,)
        row = self._one(sql, params)
        return int(row["n"])

    def category_totals_all(self, user_id: int | None = None) -> list[sqlite3.Row]:
        sql = "SELECT category, SUM(amount_cents) AS amount_cents FROM expenses"
        params: tuple[Any, ...] = ()
        if user_id is not None:
            sql += " WHERE user_id = ?"
            params = (user_id,)
        sql += " GROUP BY category ORDER BY amount_cents DESC"
        return self._rows(sql, params)

    def month_total(
        self, start: str, end_exclusive: str, user_id: int | None = None
    ) -> int:
        sql = "SELECT COALESCE(SUM(amount_cents), 0) AS t FROM expenses"
        params: list[Any] = []
        clauses = ["date >= ?", "date < ?"]
        params.extend((start, end_exclusive))
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        row = self._one(sql + " WHERE " + " AND ".join(clauses), params)
        return int(row["t"])

    def month_category_totals(
        self, start: str, end_exclusive: str, user_id: int | None = None
    ) -> list[sqlite3.Row]:
        sql = "SELECT category, SUM(amount_cents) AS amount_cents FROM expenses"
        params: list[Any] = [start, end_exclusive]
        clauses = ["date >= ?", "date < ?"]
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        sql += " WHERE " + " AND ".join(clauses)
        sql += " GROUP BY category ORDER BY amount_cents DESC"
        return self._rows(sql, params)
