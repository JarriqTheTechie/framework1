import sqlite3
import time
from typing import Any

from framework1.core_services.Database import Database
from framework1.database.QueryBuilder import QueryBuilder


def dict_factory(cursor, row):
    """Convert row to dictionary."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class Sqlite3Database(Database):
    connection = None
    connection_string: str = ""
    results: list[dict[str, Any]] = []

    def __init__(self):
        super().__init__()

    def connect(self):
        self.connection = sqlite3.connect(
            self.connection_string
        )
        self.cursor = self.connection.cursor()
        return self.cursor

    def query(self, query_str: str | QueryBuilder, *args):
        if not isinstance(query_str, str):
            query_str, args = query_str.get()

        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            params = tuple(args[0])
        else:
            params = tuple(args)

        cur = self.connect()
        start_time = time.perf_counter()
        try:
            cur.execute(query_str, params)
            columns = [column[0] for column in self.cursor.description]
            self.results = [self.DotDict(dict(zip(columns, row))) for row in self.cursor.fetchall()]
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._log_query(query_str, params, elapsed_ms)
            return self.results
        finally:
            self._cleanup()

    def save(self, query_str: str, *args):
        self.connect().execute(query_str, *args)
        self.connection.commit()
        return None

    def _cleanup(self):
        try:
            if getattr(self, "cursor", None):
                self.cursor.close()
            if getattr(self, "connection", None):
                self.connection.close()
        except Exception:
            pass
