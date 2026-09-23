from __future__ import annotations

import sqlite3
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "career_quest.db"


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def database_ready() -> bool:
    if not DB_PATH.exists():
        return False
    try:
        with connect() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM employees"
            ).fetchone()[0] > 0
    except sqlite3.DatabaseError:
        return False
