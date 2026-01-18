import pprint
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Any, Generator

import _mysql_connector
import mysql.connector

from framework1.core_services.Database import Database
from framework1.database.QueryBuilder import QueryBuilder
import logging


class MySqlDatabase(Database):
    connection = None
    connection_string: str = ""
    connection_dict: dict = {}
    results: list[dict[str, Any]] = []

    def __init__(self):
        super().__init__()

    def connect(self):
        # Allow optional pooling settings if provided in connection_dict
        connect_kwargs = self.connection_dict.copy()
        pool_name = connect_kwargs.pop("pool_name", None)
        pool_size = connect_kwargs.pop("pool_size", None)
        if pool_name:
            connect_kwargs["pool_name"] = pool_name
        if pool_size:
            connect_kwargs["pool_size"] = pool_size

        self.connection = mysql.connector.connect(**connect_kwargs)
        self.cursor = self.connection.cursor(dictionary=True)
        return self.cursor

    def query(self, query_str: str | QueryBuilder, *args):
        if not isinstance(query_str, str):
            query_str, args = query_str.get()

        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            args = tuple(args[0])
        else:
            args = tuple(args)

        try:
            start_time = time.perf_counter()
            cur = self.connect()
            cur.execute(query_str, args)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._log_query(query_str, args, elapsed_ms)
            results = [self.DotDict(row) for row in cur.fetchall()]
            self.results = results
            return results
        except mysql.connector.errors.ProgrammingError as e:
            self.logger.error(f"ProgrammingError: {e}")
            raise
        finally:
            self._cleanup()

    def pquery(self, queries, *args):
        if isinstance(queries, dict):
            queries = [{k: v} for k, v in queries.items()]

        keys = []
        for key in queries:
            keys.append(list(key.keys())[0])

        merged = {}
        for d in queries:
            merged |= d

        queries = [f"{v}" for k, v in merged.items()]

        params = list(args)
        if len(params) == 1 and isinstance(params[0], (list, tuple)):
            params = list(params[0])

        total_placeholders = sum(query.count('%s') for query in queries)
        if total_placeholders != len(params):
            raise ValueError(f"Expected {total_placeholders} parameters for pquery, received {len(params)}.")

        final_query = "; ".join(queries)

        cur = self.connect()
        start_time = time.perf_counter()
        try:
            cur.execute(final_query, tuple(params))
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._log_query(final_query, params, elapsed_ms, event_name="sql_pquery")

            all_results = []
            resultset = cur.fetchall()
            all_results.append({keys[0]: [self.DotDict(row) for row in resultset]})

            key_position = 1
            while cur.nextset():
                resultset = cur.fetchall()
                all_results.append({keys[key_position]: [self.DotDict(row) for row in resultset]})
                key_position += 1
        except mysql.connector.errors.ProgrammingError as e:
            self.logger.error(final_query)
            raise
        finally:
            self._cleanup()

        return all_results

    def save(self, table: str, data: dict[str, Any], where: dict[str, Any] = None, primary_key: str = "id"):
        if not data:
            raise ValueError("No data provided.")

        cursor = self.connect()
        

        if where:
            # UPDATE path
            set_clause = ", ".join(f"`{k}` = %s" for k in data.keys())
            where_clause = " AND ".join(f"`{k}` = %s" for k in where.keys())
            sql = f"UPDATE `{table}` SET {set_clause} WHERE {where_clause}"
            values = tuple(data.values()) + tuple(where.values())
            start_time = time.perf_counter()
            cursor.execute(sql, values)
            self.connection.commit()
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._log_query(sql, values, elapsed_ms)
            return self.query(f"SELECT * FROM `{table}` WHERE {where_clause}", *where.values())[
                0] if cursor.rowcount else None
        else:
            # INSERT path
            fields = ", ".join(f"`{k}`" for k in data.keys())
            placeholders = ", ".join(["%s"] * len(data))
            values = tuple(data.values())
            sql = f"INSERT INTO `{table}` ({fields}) VALUES ({placeholders})"
            start_time = time.perf_counter()
            cursor.execute(sql, values)
            self.connection.commit()
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._log_query(sql, values, elapsed_ms)
            inserted_id = cursor.lastrowid
            if inserted_id:
                return self.query(f"SELECT * FROM `{table}` WHERE `{primary_key}` = %s", inserted_id)[0]
            return None

    def _cleanup(self):
        try:
            if getattr(self, "cursor", None):
                self.cursor.close()
            if getattr(self, "connection", None) and self.connection.is_connected():
                self.connection.close()
        except Exception:
            pass

    @contextmanager
    def transaction(self) -> Generator[mysql.connector.connection.MySQLConnection, None, None]:
        """
        A context manager for managing transactions.
        Commits the transaction on successful execution of the block
        or rolls back if an exception occurs.
        """
        try:
            if not self.connection or not self.connection.is_connected():
                self.connect()
            self.connection.start_transaction()
            print("Transaction started.")
            yield self.connection
            self.connection.commit()
            print("Transaction committed.")
        except Exception as e:
            if self.connection:
                self.connection.rollback()
                print("Transaction rolled back due to error:", e)
            raise
        finally:
            if self.cursor:
                self.cursor.close()
            if self.connection and self.connection.is_connected():
                self.connection.close()
                print("Database connection closed.")
