import importlib
import inspect
import sys
import os
from pathlib import Path
from flask import Response
import io
import csv
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        model_ref = getattr(table_cls, "model", None)
        if model_ref:
            if isinstance(model_ref, type):
                model_name = model_ref.__name__
            else:
                # Some tables assign an ActiveRecord instance to `model`
                # (for example via configure_export_context). Index by class name.
                model_name = model_ref.__class__.__name__
            by_model[model_name] = table_cls

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


class _RenderedTableHtmlParser(HTMLParser):
    def __init__(self, target_table_id: str = None):
        super().__init__(convert_charrefs=True)
        self.target_table_id = target_table_id
        self.in_table = False
        self.table_depth = 0
        self.section = None
        self.in_row = False
        self.cell_tag = None
        self.cell_buffer = []
        self.current_row = []
        self.header_rows = []
        self.body_rows = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs or [])
        if tag == "table":
            if not self.in_table:
                if self.target_table_id and attrs_dict.get("id") != self.target_table_id:
                    return
                self.in_table = True
                self.table_depth = 1
                return
            self.table_depth += 1
            return

        if not self.in_table:
            return

        if tag in {"thead", "tbody"}:
            self.section = tag
            return

        if tag == "tr":
            self.in_row = True
            self.current_row = []
            return

        if self.in_row and tag in {"th", "td"}:
            self.cell_tag = tag
            self.cell_buffer = []
            return

        if self.cell_tag and tag == "br":
            self.cell_buffer.append("\n")

    def handle_data(self, data):
        if self.in_table and self.cell_tag:
            self.cell_buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "table" and self.in_table:
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_table = False
                self.table_depth = 0
            return

        if not self.in_table:
            return

        if tag in {"thead", "tbody"}:
            self.section = None
            return

        if tag in {"th", "td"} and self.cell_tag == tag:
            text = "".join(self.cell_buffer)
            text = " ".join(text.replace("\n", " ").split())
            self.current_row.append(text)
            self.cell_tag = None
            self.cell_buffer = []
            return

        if tag == "tr" and self.in_row:
            if self.current_row:
                target = self.body_rows
                if self.section == "thead" or any(cell for cell in self.current_row):
                    if self.section == "thead":
                        target = self.header_rows
                target.append(self.current_row)
            self.current_row = []
            self.in_row = False


def _normalize_tabular_rows(headers: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    width = max([len(headers)] + [len(r) for r in rows] + [0])
    if width == 0:
        return [], []
    if not headers:
        headers = [f"Column {i + 1}" for i in range(width)]
    elif len(headers) < width:
        headers = headers + [f"Column {i + 1}" for i in range(len(headers), width)]

    normalized_rows = []
    for row in rows:
        if len(row) < width:
            row = row + [""] * (width - len(row))
        elif len(row) > width:
            row = row[:width]
        normalized_rows.append(row)
    return headers, normalized_rows


def _table_markup_to_csv_bytes(markup, table_id: str) -> bytes:
    parser = _RenderedTableHtmlParser(target_table_id=table_id)
    parser.feed(str(markup))

    headers = parser.header_rows[0] if parser.header_rows else []
    rows = parser.body_rows if parser.body_rows else []
    if not rows and parser.header_rows[1:]:
        rows = parser.header_rows[1:]
    headers, rows = _normalize_tabular_rows(headers, rows)

    out = io.StringIO()
    writer = csv.writer(out)
    if headers:
        writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return out.getvalue().encode("utf-8")


def _table_markup_to_rows(markup, table_id: str) -> tuple[list[str], list[list[str]]]:
    parser = _RenderedTableHtmlParser(target_table_id=table_id)
    parser.feed(str(markup))

    headers = parser.header_rows[0] if parser.header_rows else []
    rows = parser.body_rows if parser.body_rows else []
    if not rows and parser.header_rows[1:]:
        rows = parser.header_rows[1:]
    headers, rows = _normalize_tabular_rows(headers, rows)
    return headers, rows


def _as_plain_record_list(rows) -> list[dict]:
    if rows is None:
        return []
    if hasattr(rows, "to_list_dict"):
        try:
            return rows.to_list_dict()
        except Exception:
            pass
    out = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
        elif hasattr(row, "to_dict"):
            out.append(row.to_dict())
        else:
            try:
                out.append(dict(row))
            except Exception:
                out.append({})
    return out


def _load_table_rows_without_pagination(table) -> list[dict]:
    query = getattr(table, "query", None)
    if query is None:
        return []

    if hasattr(query, "all"):
        try:
            return _as_plain_record_list(query.all())
        except Exception:
            pass

    if hasattr(query, "db") and hasattr(query, "get"):
        try:
            return _as_plain_record_list(query.db.query(*query.get()))
        except Exception:
            return []

    return []


def _derive_required_relations_from_schema(table) -> list[str]:
    relations = set()
    try:
        fields = table.schema() or []
    except Exception:
        fields = []

    for field in fields:
        name = getattr(field, "name", lambda: "")()
        text = str(name or "")
        if "." in text:
            rel = text.split(".", 1)[0].strip()
            if rel:
                relations.add(rel)
    return sorted(relations)


def _optimize_export_query_relations(table):
    query = getattr(table, "query", None)
    if not query:
        return

    explicit_with_only = getattr(table, "export_with_only", None)
    if explicit_with_only is None:
        needed_relations = _derive_required_relations_from_schema(table)
    else:
        needed_relations = list(explicit_with_only or [])

    explicit_without = list(getattr(table, "export_without", []) or [])

    if hasattr(query, "with_only"):
        try:
            query.with_only(needed_relations)
        except Exception:
            pass
    if explicit_without and hasattr(query, "without"):
        try:
            query.without(explicit_without)
        except Exception:
            pass
    if hasattr(query, "without_appends"):
        try:
            query.without_appends()
        except Exception:
            pass


def _ensure_export_ordering(query, table):
    if not getattr(query, "order_by_clauses", None):
        fallback_order_column = (
            getattr(getattr(query, "__class__", None), "__primary_key__", None)
            or getattr(table, "key_id", None)
            or "id"
        )
        try:
            query = query.order_by(fallback_order_column, "asc")
        except Exception:
            pass
    return query


def _paginate_query_rows(query_seed, table, chunk_size: int, workers: int = 1) -> tuple[int, dict[int, list[dict]]]:
    def fetch_page(page_no: int, count_total: bool = False):
        q = _ensure_export_ordering(query_seed.clone(), table)
        page_result = q.paginate(page_no, chunk_size, count_total=count_total)
        return page_no, page_result, _as_plain_record_list(getattr(page_result, "items", []) or [])

    # Sequential mode: avoid COUNT(*) by walking pages until has_next=False.
    if workers <= 1:
        rows_by_page = {}
        page_no = 1
        while True:
            _, page_result, rows = fetch_page(page_no, count_total=False)
            rows_by_page[page_no] = rows
            if not getattr(page_result, "has_next", False):
                break
            page_no += 1
        return page_no, rows_by_page

    # Concurrent mode: first page computes total pages, then fan out.
    _, first_page, first_rows = fetch_page(1, count_total=True)
    total_pages = int(getattr(first_page, "last_page", 1) or 1)
    rows_by_page = {1: first_rows}

    if total_pages <= 1:
        return total_pages, rows_by_page

    with ThreadPoolExecutor(max_workers=workers) as pool:
        page_numbers = list(range(2, total_pages + 1))
        futures = {pool.submit(fetch_page, p, False): p for p in page_numbers}
        for fut in as_completed(futures):
            p, _, rows = fut.result()
            rows_by_page[p] = rows

    return total_pages, rows_by_page


def _export_table_via_rendered_pages(table_cls, table, chunk_size: int, workers: int = 1) -> bytes:
    query_seed = getattr(table, "query", None)
    if query_seed is None or not hasattr(query_seed, "clone"):
        # Fallback for non-cloneable query objects.
        table.pagination = None
        table.data = _load_table_rows_without_pagination(table)
        return _table_markup_to_csv_bytes(table.render(), table.__class__.__name__)

    total_pages, rows_by_page = _paginate_query_rows(query_seed, table, chunk_size, workers)

    # Reuse the current table instance and swap in page data.
    render_table = table
    render_table._export_mode = True
    headers = []
    all_rows = []
    table_id = render_table.__class__.__name__

    for page_no in range(1, total_pages + 1):
        render_table.pagination = None
        render_table.data = rows_by_page.get(page_no, [])
        page_headers, page_rows = _table_markup_to_rows(render_table.render(), table_id)
        if page_headers and not headers:
            headers = page_headers
        all_rows.extend(page_rows)

    headers, all_rows = _normalize_tabular_rows(headers, all_rows)
    out = io.StringIO()
    writer = csv.writer(out)
    if headers:
        writer.writerow(headers)
    for row in all_rows:
        writer.writerow(row)
    return out.getvalue().encode("utf-8")


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

    export_token = request.input("__f1_export_token")
    if export_token:
        try:
            from .export_state import get_export_query
            snap_query = get_export_query(export_token, table_cls.__name__)
            if snap_query is not None:
                table.query = snap_query
        except Exception:
            pass

    _optimize_export_query_relations(table)

    # Export should represent the rendered DSL using paginated page fetches,
    # then merge all rendered rows into a single CSV.
    default_chunk = int(getattr(table, "export_chunk", 200) or 200)
    default_workers = int(getattr(table, "export_concurrency", 1) or 1)
    chunk_size = max(1, int(request.integer("chunk", default_chunk) or default_chunk))
    workers = max(1, min(8, int(request.integer("concurrency", default_workers) or default_workers)))
    if table.query:
        try:
            q = table.query.clone() if hasattr(table.query, "clone") else table.query
            if hasattr(q, "remove_limit"):
                q.remove_limit()
            if hasattr(q, "offset_count"):
                q.offset_count = None
            if hasattr(q, "rows_fetch"):
                q.rows_fetch = None
            table.query = q
        except Exception:
            pass

    csv_bytes = _export_table_via_rendered_pages(table_cls, table, chunk_size, workers)
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
