import logging
import os
import pprint
import types
from typing import Protocol
from flask import session, g, request, has_app_context
from blinker import Namespace
from framework1.database.QueryBuilder import QueryBuilder
import re

my_signals = Namespace()
query_ran = my_signals.signal('query_ran')


def extract_table_names(sql):
    sql_clean = " ".join(sql.strip().split())

    # Matches tables after FROM or JOIN
    pattern = r"(?:from|join)\s+([a-zA-Z0-9_.]+)"
    matches = re.findall(pattern, sql_clean, re.IGNORECASE)

    return list(dict.fromkeys(matches))  # remove duplicates, preserve order


class NoResultsFound(Exception):
    # Custom exception for no results found returns text "Query returned no results"
    def __init__(self, message="Query returned no results"):
        super().__init__(message)


class Database(Protocol):
    connection = None
    connection_string: str = ""
    connection_dict: dict = {}
    results = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logging_enabled = os.getenv("ORM_DEBUG", 'false').lower() == "true"
        self.logger = logging.getLogger("orm.sql")
        if not self.logger.handlers:  # prevent duplicate handlers
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"
            ))
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

    def _log_query(self, sql: str, params: tuple, elapsed_ms: float, event_name: str = "sql_query"):
        self.send_query_to_singleton_object(elapsed_ms, params, sql)

        if self.logging_enabled:
            log_entry = {
                "event": event_name,
                "sql": sql,
                "params": params,
                "elapsed_ms": round(elapsed_ms, 2),
                "database": self.__class__,
                "tables": extract_table_names(sql)
            }
            # pretty print dict instead of raw string
            self.logger.debug("\n" + pprint.pformat(log_entry, indent=2, width=80, compact=False) + "\n")

    def send_query_to_singleton_object(self, elapsed_ms, params, sql):
        try:
            from app import app
        except ImportError:
            return
        if not app:
            return

        if has_app_context():
            from framework1 import get_singleton_object
            request_id = request.cookies.get("request_id", "")

            if session.get("impersonating"):
                user_fullname = session.get("impersonator")
            else:
                user_fullname = session.get("FullName", "User without session")

            if not hasattr(g, "queries"):
                g.queries = []
                g.queries.append({
                    "username": user_fullname,
                    "path": request.path or "No Path",
                    "event": "sql_query",
                    "sql": sql,
                    "params": params,
                    "tables": extract_table_names(sql),
                    "elapsed_ms": round(elapsed_ms, 2),
                    "database": self.__class__,
                    "request_id": request_id,
                    "session": request.cookies.get("session")
                })

            else:
                g.queries.append({
                    "username": user_fullname,
                    "path": request.path or "No Path",
                    "event": "sql_query",
                    "sql": sql,
                    "params": params,
                    "tables": extract_table_names(sql),
                    "elapsed_ms": round(elapsed_ms, 2),
                    "database": self.__class__,
                    "request_id": request_id,
                    "session": request.cookies.get("session")
                })

    class DotDict(dict):
        def __getattr__(self, key):
            return self.get(key)

        def __setattr__(self, key, value):
            self[key] = value

        def __delattr__(self, key):
            del self[key]

    def dict_to_namespace(self, d):
        return types.SimpleNamespace(**{
            k: self.dict_to_namespace(v) if isinstance(v, dict) else v
            for k, v in d.items()
        })

    def requires_commit(self, query: str):
        return query.lower().startswith(("insert", "update", "delete"))

    def connect(self):
        pass

    def query(self, sql, params=None):
        pass

    def save(self, query, table_name, values):
        pass

    def results_or_fail(self, query_str: str | QueryBuilder, *args, fallback=None):
        self.results = self.query(query_str, *args)
        if not self.results:
            if fallback:
                return fallback()
            raise NoResultsFound()
        results = []
        for result in self.results:
            results.append(self.DotDict(result))
        self.results = results
        return self.results

    def pquery(self, queries, *args):
        ...
