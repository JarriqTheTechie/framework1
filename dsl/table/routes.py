import importlib
import inspect
import sys
import os
from pathlib import Path
from flask import Response
import io
import csv

from framework1.core_services.Request import Request
from framework1.service_container._Injector import injectable_route
from framework1.dsl.table.core import Table
from app import app

_TABLE_REGISTRY_CACHE = None


def _discover_tables(base_dirs=None):
    """Locate Table subclasses in legacy handler paths and DDD domain UI paths."""
    tables = []
    base_dirs = base_dirs or ["lib/handlers", "lib/domain"]

    for base_dir in base_dirs:
        root = Path(base_dir)
        if not root.exists():
            continue

        project_root = root.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        glob_pattern = "tables/*.py" if "handlers" in root.parts else "*/ui/tables/*.py"

        for file in root.rglob(glob_pattern):
            if file.name == "__init__.py":
                continue
            module_path = ".".join(file.with_suffix("").relative_to(project_root).parts)
            try:
                module = importlib.import_module(module_path)
            except Exception:
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Table) and obj is not Table and obj.__module__ == module.__name__:
                    tables.append(obj)
    return tables


def _get_table_registry(force_refresh=False):
    """Return cached table registry keyed by table and model names."""
    global _TABLE_REGISTRY_CACHE
    if _TABLE_REGISTRY_CACHE is not None and not force_refresh:
        return _TABLE_REGISTRY_CACHE

    tables = _discover_tables()
    by_table = {}
    by_model = {}

    for table_cls in tables:
        by_table[table_cls.__name__] = table_cls
        model_cls = getattr(table_cls, "model", None)
        if model_cls:
            by_model[model_cls.__name__] = table_cls

    _TABLE_REGISTRY_CACHE = {
        "tables": tables,
        "by_table": by_table,
        "by_model": by_model,
    }
    return _TABLE_REGISTRY_CACHE


def _resolve_table_class(table_name=None, model_name=None):
    registry = _get_table_registry()
    if table_name:
        table_cls = registry["by_table"].get(table_name)
        if table_cls:
            return table_cls
    if model_name:
        return registry["by_model"].get(model_name)
    return None


@injectable_route(app, "/f1/export-csv-chunked", methods=["GET"])
def TableExportCsvChunked(request: Request):
    """
    Universal server-side CSV export that paginates in chunks to keep memory and DB load manageable.
    Requires model.__exportable__ = True.
    """
    table_name = request.input("table")
    model_name = request.input("model")
    if not table_name and not model_name:
        return {"success": False, "message": "Table or model required"}

    chunk_size = request.integer("chunk", 200)

    table_cls = _resolve_table_class(table_name=table_name, model_name=model_name)

    if not table_cls:
        return {"success": False, "message": "Unknown table/model"}

    model_cls = getattr(table_cls, "model", None)
    if not model_cls or not getattr(model_cls, "__exportable__", False):
        return {"success": False, "message": "Model not exportable"}

    if hasattr(table_cls, "configure_export_context"):
        try:
            table_cls = table_cls.configure_export_context()
        except Exception:
            # If a table-specific export context hook fails, fall back to the base class
            # so export behavior remains backward-compatible for tables without this hook.
            pass

    table = table_cls()
    if not table.query:
        return {"success": False, "message": "No query available for export"}

    fields = [
        f for f in table.schema()
        if hasattr(f, "_hidden")
        and not (callable(f._hidden) and f._hidden({}))
        and not (isinstance(f._hidden, bool) and f._hidden)
    ]
    headers = [f.header() for f in fields]

    def value_from_field(field, rec_dict):
        val = rec_dict
        if "." in field.name():
            for part in field.name().split("."):
                if isinstance(val, dict):
                    val = val.get(part, "")
                else:
                    val = getattr(val, part, "")
                if val in (None, ""):
                    break
        else:
            val = rec_dict.get(field.name(), "")
        if hasattr(field, "_format_value"):
            try:
                return field._format_value(val, rec_dict)
            except Exception:
                # Keep export resilient even when a column formatter depends on
                # request-only or page-only context that is unavailable in export mode.
                return val
        return val

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    page = 1
    while True:
        try:
            pagination = table.query.clone().paginate(page, chunk_size)
        except Exception:
            break

        items = getattr(pagination, "items", []) or []
        if not items:
            break

        for rec in items:
            rec_dict = rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)
            writer.writerow([value_from_field(f, rec_dict) for f in fields])

        if not getattr(pagination, "has_next", False):
            break
        page += 1

    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename=\"{table_cls.__name__}.csv\"'}
    )


@injectable_route(app, "/f1/export-excel", methods=["GET"])
def TableExportExcel(request: Request):
    # Disabled in favor of chunked CSV export
    return {"success": False, "message": "Excel export disabled. Use /f1/export-csv-chunked"}


@injectable_route(app, "/f1/delete-bulk", methods=["POST", "DELETE"])
def TableDeleteBulk(request: Request):
    ids = request.to_list("ids", cast=int)
    model_name = request.input("model")
    table_name = request.input("table")
    if not ids or (not model_name and not table_name):
        return {"success": False, "message": "Invalid request"}

    table_cls = _resolve_table_class(table_name=table_name, model_name=model_name)

    if not table_cls or not getattr(table_cls, "model", None):
        return {"success": False, "message": "Unknown table/model"}

    table_cls.model().where_in("id", ids).delete()
    return {"success": True}


@injectable_route(app, "/f1/db/plan-sample", methods=["GET"])
def TablePlanSample(request: Request):
    """
    Debug-only DB plan sampling endpoint for table-backed routes.
    Query params:
      - table=PaymentTable (or model=Payment)
      - page=1
      - per_page=25
      - mode=both|count|data
    """
    enabled = app.debug or os.getenv("ORM_PLAN_ENDPOINT", "false").lower() == "true"
    if not enabled:
        return {"success": False, "message": "Plan sampling disabled"}, 403

    table_name = request.input("table")
    model_name = request.input("model")
    if not table_name and not model_name:
        return {"success": False, "message": "Table or model required"}, 400

    table_cls = _resolve_table_class(table_name=table_name, model_name=model_name)
    if not table_cls:
        return {"success": False, "message": "Unknown table/model"}, 404

    mode = str(request.input("mode", "both") or "both").strip().lower()
    if mode not in {"both", "count", "data"}:
        mode = "both"

    page = request.integer("page", 1)
    per_page = request.integer("per_page", 25)

    table = table_cls()
    query = getattr(table, "query", None)
    if not query:
        return {"success": False, "message": "No query available for table"}, 400

    db = getattr(query, "db", None)
    if not db:
        return {"success": False, "message": "No database instance on query"}, 400

    out = {
        "success": True,
        "table": table_cls.__name__,
        "mode": mode,
        "page": page,
        "per_page": per_page,
        "driver": getattr(query, "__driver__", None),
    }

    if mode in {"both", "count"}:
        try:
            count_q = query.clone()
            if hasattr(count_q, "_apply_scopes_once_for_read"):
                count_q._apply_scopes_once_for_read()
            if hasattr(count_q, "_apply_explicit_select_if_safe"):
                count_q._apply_explicit_select_if_safe()
            if hasattr(count_q, "_build_paginate_count_query"):
                count_q = count_q._build_paginate_count_query()
            else:
                count_q.columns = ["COUNT(*) as count"]
                count_q.remove_ordering()
                count_q.remove_limit()
            count_sql, count_params = count_q.get()
            out["count"] = {
                "sql": count_sql,
                "params": list(count_params or []),
                "fingerprint": db._sql_fingerprint(count_sql) if hasattr(db, "_sql_fingerprint") else None,
                "plan": db.explain_sql(count_sql, count_params),
            }
        except Exception as e:
            out["count_error"] = str(e)

    if mode in {"both", "data"}:
        try:
            data_q = query.clone()
            if hasattr(data_q, "_apply_scopes_once_for_read"):
                data_q._apply_scopes_once_for_read()
            if hasattr(data_q, "_apply_explicit_select_if_safe"):
                data_q._apply_explicit_select_if_safe()
            data_q.paginate(page, per_page)
            data_sql, data_params = data_q.get()
            out["data"] = {
                "sql": data_sql,
                "params": list(data_params or []),
                "fingerprint": db._sql_fingerprint(data_sql) if hasattr(db, "_sql_fingerprint") else None,
                "plan": db.explain_sql(data_sql, data_params),
            }
        except Exception as e:
            out["data_error"] = str(e)

    return out
