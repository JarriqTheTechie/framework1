import pprint
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any
import logging
import pyodbc

from framework1.core_services.Database import Database
from framework1.database.QueryBuilder import QueryBuilder


def dict_factory(cursor, row):
    """Convert row to dictionary."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def handle_unsupported_dtype(v):
    return str(v)


def get_column_names(cursor):
    return [column[0] for column in cursor.description]


def result_to_dotdict(columns, results, dotdict_cls):
    return [dotdict_cls(dict(zip(columns, row))) for row in results]


class MSSQLDatabase(Database):
    connection = None
    connection_string: str = ""
    results: list[dict[str, Any]] = []

    def __init__(self):
        super().__init__()

    def connect(self):
        self.connection = pyodbc.connect(
            self.connection_string
        )
        self.connection.add_output_converter(-16, handle_unsupported_dtype)
        self.cursor = self.connection.cursor()
        return self.cursor

    def query(self, query_str: str | QueryBuilder, *args: tuple) -> list[dict[str, Any]]:
        if not isinstance(query_str, str):
            query_str, args = query_str.get()

        query_str = query_str.replace("%s", "?")
        start_time = time.perf_counter()
        cur = self.connect()
        cur.execute(query_str, *args)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if len(args) == 0:
            debug_view_args = None
        else:
            debug_view_args = args[0]
        self._log_query(query_str, params=debug_view_args, elapsed_ms=elapsed_ms)
        try:
            columns = get_column_names(self.cursor)  # Get column names
            raw_results = self.cursor.fetchall()
            self.results = result_to_dotdict(columns, raw_results, self.DotDict)
        except TypeError:
            self.results = []
        finally:
            self._cleanup()
        return self.results

    def pquery(self, queries, *args):
        results_as_tuple = []

        keys = []
        for key in queries:
            keys.append(list(key.keys())[0])

        merged = {}
        for d in queries:
            merged |= d

        queries = [f"{v}" for k, v in merged.items()]

        # Replace %s with ? for MSSQL
        queries = [q.replace("%s", "?") for q in queries]

        # Join queries with semicolons
        joined = "; ".join(queries)

        start_time = time.perf_counter()

        # Execute the batch query
        cursor = self.connect()
        if args:
            results = cursor.execute(joined, *args)
        else:
            if joined:
                results = cursor.execute(joined)
            else:
                return ([])

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._log_query(joined, params=args if args else (), elapsed_ms=elapsed_ms, event_name="sql_pquery")

        # Get first result set
        first_resultset = cursor.fetchall()
        columns = get_column_names(cursor)
        results_as_tuple.append({keys[0]: result_to_dotdict(columns, first_resultset, self.DotDict)})

        # Get subsequent result sets
        key_position = 1
        while cursor.nextset():
            columns = [column[0] for column in cursor.description]
            results_as_tuple.append({keys[key_position]: result_to_dotdict(columns, cursor.fetchall(), self.DotDict)})
            key_position += 1
        self._cleanup()
        return results_as_tuple

    def save(
            self,
            table: str,
            data: dict[str, Any],
            where: dict[str, Any] = None,
            primary_key: str = "id"
    ):
        if not data:
            raise ValueError("No data provided.")

        cursor = self.connect()

        if where:
            # UPDATE logic with WHERE IN support
            where_clause_parts = []
            values = []

            for k, v in where.items():
                if isinstance(v, list):  # If the value is a list, use IN clause
                    where_clause_parts.append(f"[{k}] IN ({','.join(['?'] * len(v))})")
                    values.extend(v)  # Add all values from the list to the values
                else:
                    where_clause_parts.append(f"[{k}] = ?")
                    values.append(v)

            where_clause = " AND ".join(where_clause_parts)
            set_clause = ", ".join(f"[{k}] = ?" for k in data.keys())
            sql = f"UPDATE [{table}] SET {set_clause} WHERE {where_clause}"
            values = tuple(data.values()) + tuple(values)
            start_time = time.perf_counter()
            cursor.execute(sql, values)
            self.connection.commit()
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._log_query(sql, values, elapsed_ms)

            if cursor.rowcount:
                where_params = tuple(where.values())
                select_sql = f"SELECT * FROM [{table}] WHERE {where_clause}"
                # return self.query(select_sql, *values)[0]
            return None
        else:
            # INSERT logic
            fields = ", ".join(f"[{k}]" for k in data.keys())
            placeholders = ", ".join(["?"] * len(data))
            values = tuple(data.values())
            sql = f"INSERT INTO [{table}] ({fields}) VALUES ({placeholders})"
            start_time = time.perf_counter()
            cursor.execute(sql, values)
            self.connection.commit()
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._log_query(sql, values, elapsed_ms)

            # Fetch last inserted row (assumes IDENTITY column is `primary_key`)
            identity_query = f"SELECT IDENT_CURRENT('{table}') AS [{primary_key}]"
            identity_result = self.query(identity_query)[0]
            inserted_id = identity_result[primary_key]

            if inserted_id:
                return self.query(f"SELECT * FROM [{table}] WHERE [{primary_key}] = ?", inserted_id)[0]
            return None

    def _cleanup(self):
        try:
            if getattr(self, "cursor", None):
                self.cursor.close()
            if getattr(self, "connection", None):
                self.connection.close()
        except Exception:
            pass
