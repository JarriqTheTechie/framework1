import threading
import time
import uuid

_EXPORT_QUERY_CACHE = {}
_EXPORT_QUERY_LOCK = threading.Lock()
_EXPORT_QUERY_TTL_SECONDS = 600
_EXPORT_QUERY_MAX_ENTRIES = 512


def _prune_locked(now_ts: float):
    expired = [
        key
        for key, value in _EXPORT_QUERY_CACHE.items()
        if (now_ts - value.get("created_at", 0)) > _EXPORT_QUERY_TTL_SECONDS
    ]
    for key in expired:
        _EXPORT_QUERY_CACHE.pop(key, None)

    # Hard cap to prevent unbounded growth in long-lived processes.
    if len(_EXPORT_QUERY_CACHE) > _EXPORT_QUERY_MAX_ENTRIES:
        oldest = sorted(
            _EXPORT_QUERY_CACHE.items(),
            key=lambda item: item[1].get("created_at", 0),
        )
        for key, _ in oldest[: len(_EXPORT_QUERY_CACHE) - _EXPORT_QUERY_MAX_ENTRIES]:
            _EXPORT_QUERY_CACHE.pop(key, None)


def register_export_query(table_name: str, query) -> str | None:
    if query is None or not hasattr(query, "clone"):
        return None

    try:
        snapshot = query.clone()
        if hasattr(snapshot, "remove_limit"):
            snapshot.remove_limit()
    except Exception:
        return None

    token = uuid.uuid4().hex
    now_ts = time.time()
    with _EXPORT_QUERY_LOCK:
        _prune_locked(now_ts)
        _EXPORT_QUERY_CACHE[token] = {
            "created_at": now_ts,
            "table_name": table_name,
            "query": snapshot,
        }
    return token


def get_export_query(token: str, table_name: str = None):
    if not token:
        return None

    now_ts = time.time()
    with _EXPORT_QUERY_LOCK:
        _prune_locked(now_ts)
        entry = _EXPORT_QUERY_CACHE.get(token)
        if not entry:
            return None
        if table_name and entry.get("table_name") != table_name:
            return None
        query = entry.get("query")

    if query is None:
        return None
    if hasattr(query, "clone"):
        try:
            return query.clone()
        except Exception:
            return query
    return query
