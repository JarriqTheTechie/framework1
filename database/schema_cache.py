import re
from threading import RLock


_SCHEMA_COLUMNS_CACHE: dict[tuple[str, str, str | None, str], tuple[str, ...]] = {}
_SCHEMA_CACHE_LOCK = RLock()


def _parse_table_for_schema_lookup(table_raw: str):
    text = str(table_raw or "").strip()
    if not text:
        return None, None
    if " " in text or "(" in text or ")" in text:
        return None, None
    if "." in text:
        schema, table = text.split(".", 1)
        if not re.fullmatch(r"[A-Za-z_][\w]*", schema) or not re.fullmatch(r"[A-Za-z_][\w]*", table):
            return None, None
        return schema, table
    if not re.fullmatch(r"[A-Za-z_][\w]*", text):
        return None, None
    return None, text


def get_table_columns_cached(db, driver: str, table_raw: str):
    schema, table = _parse_table_for_schema_lookup(table_raw)
    if not db or not table:
        return None

    driver = str(driver or "").lower()
    db_key = db.__class__.__name__
    schema_key = schema or ("dbo" if driver == "mssql" else None)
    cache_key = (db_key, driver, schema_key, table)

    with _SCHEMA_CACHE_LOCK:
        cached = _SCHEMA_COLUMNS_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    try:
        if driver == "mysql":
            rows = db.query(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                """,
                table,
            )
            columns = [r.get("COLUMN_NAME") for r in rows if r.get("COLUMN_NAME")]
        elif driver == "mssql":
            rows = db.query(
                """
                SELECT c.name AS column_name
                FROM sys.columns c
                INNER JOIN sys.tables t ON t.object_id = c.object_id
                INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
                WHERE t.name = %s AND s.name = %s
                """,
                table,
                schema_key or "dbo",
            )
            columns = [r.get("column_name") for r in rows if r.get("column_name")]
        else:
            columns = None
    except Exception:
        columns = None

    if columns is not None:
        with _SCHEMA_CACHE_LOCK:
            _SCHEMA_COLUMNS_CACHE[cache_key] = tuple(columns)
    return columns

