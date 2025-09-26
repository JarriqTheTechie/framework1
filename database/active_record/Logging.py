import logging
import time
from contextlib import contextmanager
import sys

logger = logging.getLogger("orm.sql")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

@contextmanager
def query_logging(db):
    """
    Context manager that logs all queries executed inside its block.
    Accepts either an ActiveRecord model (with .db) or a Database instance.
    """
    db = getattr(model_or_db, "db", model_or_db)  # support model or db
    original_query = db.query
    original_pquery = getattr(db, "pquery", None)

    def logged_query(*args, **kwargs):
        start = time.perf_counter()
        result = original_query(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        sql, params = args if len(args) == 2 else (args[0], args[1:])
        logger.debug("[SQL] %s\n[Params] %s\n[Took] %.2f ms", sql, params, elapsed)
        return result

    def logged_pquery(*args, **kwargs):
        start = time.perf_counter()
        result = original_pquery(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        logger.debug("[PQUERY] %s\n[Params] %s\n[Took] %.2f ms", args[0], args[1:], elapsed)
        return result

    db.query = logged_query
    if original_pquery:
        db.pquery = logged_pquery

    try:
        yield
    finally:
        db.query = original_query
        if original_pquery:
            db.pquery = original_pquery