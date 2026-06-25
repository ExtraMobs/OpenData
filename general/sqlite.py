from pathlib import Path
import sqlite3


class SQLiteBase:
    _conn: sqlite3.Connection

    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(db_path)

    def close(self):
        if self._conn:
            self._conn.close()

    def execute_query(self, query: str, params=()):
        if not self._conn:
            raise RuntimeError(
                "Database connection not established. Use 'with' statement."
            )
        cursor = self._conn.cursor()
            
        cursor.execute(query, params)
        return cursor

    def commit(self):
        self._conn.commit()

    def fetch_one(self, query: str, params=()):
        if not self._conn:
            raise RuntimeError(
                "Database connection not established. Use 'with' statement."
            )
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()

    def fetch_all(self, query: str, params=()):
        if not self._conn:
            raise RuntimeError(
                "Database connection not established. Use 'with' statement."
            )
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()
