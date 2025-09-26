import types
from abc import ABC, abstractmethod
from typing import Protocol
import logging
import pprint
from framework1.database.QueryBuilder import QueryBuilder
import os

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

    def _log_query(self, sql: str, params: tuple, elapsed_ms: float):
        if self.logging_enabled:
            log_entry = {
                "event": "sql_query",
                "sql": sql,
                "params": params,
                "elapsed_ms": round(elapsed_ms, 2),
                "database": self.__class__,
            }
            # pretty print dict instead of raw string
            self.logger.debug("\n" + pprint.pformat(log_entry, indent=2, width=80, compact=False) + "\n")

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
        if query.lower().startswith(("insert", "update", "delete")):
            return True

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

    def pquery(self, queries, *args): ...
