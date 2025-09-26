import sqlite3
from typing import Any
import pyodbc

from framework1.core_services.Database import Database
from framework1.database.QueryBuilder import QueryBuilder


def dict_factory(cursor, row):
    """Convert row to dictionary."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class Sqlite3Database(Database):
    connection = None
    connection_string: str = ""
    results: list[dict[str, Any]] = []

    def connect(self):
        self.connection = sqlite3.connect(
            self.connection_string
        )
        self.cursor = self.connection.cursor()
        return self.cursor

    def query(self, query_str: str | QueryBuilder, *args):
        if not isinstance(query_str, str):
            query_str = query_str.get()
        self.connect().execute(query_str, *args)
        columns = [column[0] for column in self.cursor.description]  # Get column names
        self.results = [dict(zip(columns, row)) for row in self.cursor.fetchall()]  # Use comprehension
        return self.results

    def save(self, query_str: str, *args):
        self.connect().execute(query_str, *args)
        self.connection.commit()
        return None
