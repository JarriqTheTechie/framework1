from argparse import Action
import re

from framework1.core_services.Request import Request
from framework1.database.QueryBuilder import QueryBuilder

from .export import TableExportMixin
from .filters import TableFiltersMixin
from .pagination import TablePaginationMixin
from .render import TableRenderMixin
from .search_sort import TableSearchSortMixin


class TableBase:
    table_class = ""
    table_style = ""
    thead_class = ""  # Class for <thead>
    tbody_class = ""  # Class for <tbody>
    tr_class = ""  # Class for <tr>

    key_id = "id"
    search_key = "id"
    model = None
    persist_columns = True

    persist_sort = False
    persist_search = False
    persist_filters = False
    # Pagination tuning:
    # - "offset" (default): traditional page/per_page with COUNT + OFFSET
    # - "keyset": cursor-based pagination for stable deep-page performance
    pagination_mode = "offset"
    simple_paginate = False
    keyset_column = None
    keyset_direction = "asc"
    keyset_param = "cursor"
    # Index diagnostics:
    # - False (default): no index metadata queries
    # - True: inspect DB indexes and expose a report on the table instance
    validate_indexes = False
    # Projection tuning:
    # - False (default): keep existing SELECT behavior (typically SELECT *).
    # - True: auto-select only needed table columns for rendering/search/actions.
    optimize_select_columns = False
    # Join tuning:
    # - False (default): keep all joins as defined by model/query scopes.
    # - True: prune joins not referenced by selected/order/filter/group/having clauses.
    optimize_prune_joins = False
    # Search modes:
    # - "contains": LIKE %term% (broad match, least index-friendly)
    # - "prefix":   LIKE term% (index-friendly on standard btree indexes)
    # - "exact":    LIKE term  (exact match semantics)
    # - "full_text": uses QueryBuilder full-text helpers when supported
    search_mode = "contains"
    full_text_mode = None
    search_min_term_length = 1
    selectable = False
    master_detail_expandable = True

    filterable_fields = []
    filter_field_meta = {}
    filter_presets = {}

    search_placeholder = "Search..."

    def __init__(self, data: list[dict] = None, non_activerecord_model=None, as_dto=False, dto_target=None):
        self.pagination = None
        self.data = data
        self.query = None
        self._schema_cache = None
        self.sub_resource_table = False
        self.table_name = self.__class__.__name__

        # Cache filter metadata for quick lookups (field -> dict(label/type/operators))
        self._filter_field_meta = getattr(self, "filter_field_meta", {}) or {}

        # If a model is set, initialize its query builder
        if self.model:
            if isinstance(self.model, type):
                self.query = self.model()
            else:
                self.query = self._fresh_query_from_model(self.model)

        def _apply_request_filter_groups(query):
            if not query:
                return query
            filters = Request().grouped("filters")
            grouped_filters = {}
            for f in filters:
                group_name = f.get("group", "default") or "default"
                grouped_filters.setdefault(group_name, []).append(f)
            for group_filters in grouped_filters.values():
                query = self.apply_filter_conditions(query, group_filters)
            return query

        # Apply grouped request filters once; then allow custom query mutation if overridden.
        self.query = _apply_request_filter_groups(self.query)
        if self.modify_table_query.__func__ is not TableBase.modify_table_query:
            self.query = self.modify_table_query()

        # If a non-ActiveRecord model is passed, use it directly
        if non_activerecord_model:
            if hasattr(non_activerecord_model, "paginate"):
                self.query = non_activerecord_model
            else:
                raise TypeError("non_activerecord_model must be an instance of QueryBuilder")

        # If we have a query, apply automatic sorting
        if self.query:
            self.query = self._apply_search(self.query)
            self.query = self._apply_sorting(self.query)

        if hasattr(self, "filters"):
            self.query = self._apply_filters_grouped(self.filters(), self.query)

        if self.query:
            self.query = self._apply_select_projection(self.query)
            if getattr(self, "optimize_prune_joins", False):
                self.query = self._prune_unused_joins(self.query)
            if getattr(self, "validate_indexes", False):
                try:
                    self.index_validation_report = self.validate_index_coverage()
                except Exception:
                    self.index_validation_report = None

        # If user wants DTOs
        if as_dto and self.model and dto_target:
            self.as_dto = as_dto
            self.dto_target = dto_target

    def _fresh_query_from_model(self, model_instance):
        """
        Build a request-local query object from a model/query instance so mutable
        state (conditions/params/pagination/scopes) does not leak between requests.
        """
        query = model_instance
        if hasattr(model_instance, "clone") and callable(getattr(model_instance, "clone")):
            try:
                query = model_instance.clone()
            except Exception:
                query = model_instance

        # Preserve relation override intent when the model instance was configured
        # with helpers like `.without([...])` / `.with_only([...])`.
        if hasattr(model_instance, "_with_overrides"):
            try:
                query._with_overrides = list(getattr(model_instance, "_with_overrides") or [])
            except Exception:
                pass

        # A fresh query should re-allow scope application for this request.
        if hasattr(query, "__scopes_enabled__"):
            query.__scopes_enabled__ = True

        return query

    def schema(self):
        """Override this method to define schema."""
        return []

    def _get_schema_cached(self):
        if self._schema_cache is None:
            schema = self.schema()
            self._schema_cache = schema if schema is not None else []
        return self._schema_cache

    def _ensure_data_loaded(self, force_query_get: bool = False):
        if self.data is None and self.query is not None:
            if force_query_get or getattr(self, "pagination", None) is None:
                self.data = self.query.get()
        return self.data if self.data is not None else []

    def select_columns(self) -> list[str]:
        """
        Optional hook: add columns needed by actions/formatters that are not in schema().
        """
        return []

    def _query_has_explicit_projection(self, query) -> bool:
        columns = getattr(query, "columns", None)
        if not columns:
            return False
        return not (len(columns) == 1 and str(columns[0]).strip() == "*")

    def _collect_projection_columns(self) -> list[str]:
        from .master_detail import MasterDetailRow
        fields = self._get_schema_cached()
        columns = [self.key_id]

        for field in fields:
            if isinstance(field, MasterDetailRow):
                continue
            name = field.name()
            if name:
                columns.append(name)

        if isinstance(self.search_key, str) and self.search_key:
            columns.append(self.search_key)
        elif isinstance(self.search_key, list):
            columns.extend([c for c in self.search_key if c])

        try:
            if hasattr(self, "searchable") and self.searchable.__func__ is not TableSearchSortMixin.searchable:
                columns.extend(self.searchable() or [])
        except Exception:
            pass

        try:
            columns.extend(self.select_columns() or [])
        except Exception:
            pass

        # Stable de-duplication while preserving order
        seen = set()
        deduped = []
        for col in columns:
            key = str(col).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(col)
        return deduped

    def _extract_join_aliases(self, query) -> set[str]:
        aliases = set()
        for join_sql in getattr(query, "joins", []) or []:
            # Capture "... JOIN table alias ON ..." and "... JOIN table AS alias ON ..."
            m = re.search(r"\bJOIN\s+[^\s]+\s+(?:AS\s+)?([A-Za-z_][\w]*)\s+ON\b", str(join_sql), re.IGNORECASE)
            if m:
                aliases.add(m.group(1))
        return aliases

    def _extract_join_alias_map(self, query) -> dict[str, str]:
        alias_map = {}
        for join_sql in getattr(query, "joins", []) or []:
            text = str(join_sql)
            m = re.search(r"\bJOIN\s+[^\s]+\s+(?:AS\s+)?([A-Za-z_][\w]*)\s+ON\b", text, re.IGNORECASE)
            if m:
                alias_map[m.group(1)] = join_sql
        return alias_map

    def _is_simple_column_name(self, col: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z_][\w]*", col))

    def _normalize_projection_for_query(self, query, columns: list) -> list:
        base_table = str(getattr(query, "__table__", "") or "")
        base_alias = str(getattr(query, "alias", "") or "")
        join_aliases = self._extract_join_aliases(query)

        normalized = []
        for col in columns:
            text = str(col).strip()
            if not text:
                continue

            # Keep explicit expressions/raw aliases untouched.
            if any(token in text for token in ("(", ")", " AS ", " as ")):
                normalized.append(col)
                continue

            # Unqualified simple names get table qualification to avoid ambiguity on joined queries.
            if "." not in text and self._is_simple_column_name(text):
                if base_table:
                    normalized.append(f"{base_table}.{text}")
                else:
                    normalized.append(text)
                continue

            # Qualified columns are accepted only when qualifier is actually present in SQL scope.
            if "." in text:
                qualifier = text.split(".", 1)[0]
                if qualifier in {base_table, base_alias} or qualifier in join_aliases:
                    normalized.append(text)
                # Otherwise this is likely a relationship path (e.g., "jurisdiction.Name"), not SQL.
                continue

            normalized.append(col)

        # Final stable de-duplication after normalization
        out = []
        seen = set()
        for col in normalized:
            key = str(col).strip()
            if key in seen:
                continue
            seen.add(key)
            out.append(col)
        return out

    def _filter_projection_columns_against_model(self, query, columns: list) -> list:
        """
        Drop likely virtual/appended simple fields that are not physical model fields.
        Keeps qualified columns and raw expressions unchanged.
        """
        model_cls = getattr(query, "__class__", None)
        get_fields = getattr(model_cls, "get_fields", None)
        if not callable(get_fields):
            return columns

        try:
            model_fields = set(get_fields().keys())
        except Exception:
            return columns

        appends = set(getattr(model_cls, "__appends__", []) or [])
        filtered = []
        for col in columns:
            text = str(col).strip()
            if not text:
                continue
            if any(token in text for token in ("(", ")", " AS ", " as ")):
                filtered.append(col)
                continue
            if "." in text:
                filtered.append(col)
                continue
            if text in appends:
                continue
            if text in model_fields:
                filtered.append(col)
                continue
            # Unknown simple column: skip by default to avoid SQL errors from virtual accessors.
        return filtered

    def _apply_select_projection(self, query):
        if not getattr(self, "optimize_select_columns", False):
            return query
        if self._query_has_explicit_projection(query):
            return query
        columns = self._collect_projection_columns()
        columns = self._filter_projection_columns_against_model(query, columns)
        columns = self._normalize_projection_for_query(query, columns)
        if columns:
            query = query.select(columns)
        return query

    def _collect_required_join_qualifiers(self, query) -> set[str]:
        required = set()
        table_name = str(getattr(query, "__table__", "") or "")
        table_alias = str(getattr(query, "alias", "") or "")

        def add_from_text(sql_text: str):
            for q, _ in re.findall(r"([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)", str(sql_text or "")):
                required.add(q)

        for col in getattr(query, "columns", []) or []:
            add_from_text(str(col))

        for col, _dir in getattr(query, "order_by_clauses", []) or []:
            add_from_text(str(col))

        for _logic, cond in getattr(query, "conditions", []) or []:
            add_from_text(str(cond))

        for grp in getattr(query, "group_by_columns", []) or []:
            add_from_text(str(grp))

        for _logic, hv in getattr(query, "having_conditions", []) or []:
            add_from_text(str(hv))

        if table_name:
            required.add(table_name)
        if table_alias:
            required.add(table_alias)

        return required

    def _prune_unused_joins(self, query):
        joins = getattr(query, "joins", None)
        if not joins:
            return query

        alias_map = self._extract_join_alias_map(query)
        if not alias_map:
            return query

        required = self._collect_required_join_qualifiers(query)
        pruned = []
        for join_sql in joins:
            text = str(join_sql)
            m = re.search(r"\bJOIN\s+[^\s]+\s+(?:AS\s+)?([A-Za-z_][\w]*)\s+ON\b", text, re.IGNORECASE)
            if not m:
                # Keep unknown join shapes to avoid unsafe removal.
                pruned.append(join_sql)
                continue
            alias = m.group(1)
            if alias in required:
                pruned.append(join_sql)

        query.joins = pruned
        return query

    def _parse_table_parts(self, table_name: str):
        table_name = str(table_name or "").strip()
        if not table_name:
            return "dbo", ""
        # Strip simple alias forms: "dbo.Users AS u" / "dbo.Users u"
        base = table_name.split(" AS ")[0].split(" as ")[0].split()[0]
        if "." in base:
            schema, table = base.split(".", 1)
            return schema, table
        return "dbo", base

    def _field_leaf(self, col: str) -> str:
        text = str(col or "").strip()
        if not text:
            return ""
        if "." in text:
            return text.split(".")[-1]
        return text

    def _recommended_index_columns(self) -> list[str]:
        cols = [self._field_leaf(self.key_id)]
        cols.extend(self._field_leaf(f.name()) for f in self._get_schema_cached() if getattr(f, "_sortable", False))

        search_cols = []
        search_key = getattr(self, "search_key", None)
        if isinstance(search_key, str):
            search_cols.append(search_key)
        elif isinstance(search_key, list):
            search_cols.extend(search_key)

        try:
            if hasattr(self, "searchable") and self.searchable.__func__ is not TableSearchSortMixin.searchable:
                search_cols.extend(self.searchable() or [])
        except Exception:
            pass
        search_cols.extend(f.name() for f in self._get_schema_cached() if getattr(f, "_searchable", False))
        cols.extend(self._field_leaf(c) for c in search_cols)

        cols.extend(self._field_leaf(c) for c in (getattr(self, "filterable_fields", []) or []))

        if str(getattr(self, "pagination_mode", "offset")).lower() == "keyset":
            cols.append(self._field_leaf(getattr(self, "keyset_column", None) or self.key_id))

        out = []
        seen = set()
        for c in cols:
            if not c:
                continue
            if not re.fullmatch(r"[A-Za-z_][\w]*", c):
                continue
            if c in seen:
                continue
            seen.add(c)
            out.append(c)
        return out

    def _inspect_table_indexes(self) -> dict:
        query = getattr(self, "query", None)
        db = getattr(query, "db", None)
        driver = str(getattr(query, "__driver__", "") or "").lower()
        table_raw = str(getattr(query, "__table__", "") or "")
        schema, table = self._parse_table_parts(table_raw)
        if not db or not table:
            return {"driver": driver, "table": table_raw, "indexes": {}}

        if driver == "mysql":
            rows = db.query(
                """
                SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX
                FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                ORDER BY INDEX_NAME, SEQ_IN_INDEX
                """,
                table,
            )
            idx = {}
            for r in rows:
                name = r.get("INDEX_NAME")
                col = r.get("COLUMN_NAME")
                if not name or not col:
                    continue
                idx.setdefault(name, []).append(col)
            return {"driver": driver, "table": table, "schema": None, "indexes": idx}

        if driver == "mssql":
            rows = db.query(
                """
                SELECT i.name AS index_name, c.name AS column_name, ic.key_ordinal AS key_ordinal
                FROM sys.indexes i
                INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                INNER JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
                INNER JOIN sys.tables t ON t.object_id = i.object_id
                INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
                WHERE t.name = %s AND s.name = %s AND i.is_hypothetical = 0 AND i.type > 0
                ORDER BY i.name, ic.key_ordinal
                """,
                table,
                schema,
            )
            idx = {}
            for r in rows:
                name = r.get("index_name")
                col = r.get("column_name")
                if not name or not col:
                    continue
                idx.setdefault(name, []).append(col)
            return {"driver": driver, "table": table, "schema": schema, "indexes": idx}

        return {"driver": driver, "table": table_raw, "indexes": {}}

    def validate_index_coverage(self) -> dict:
        recommendations = self._recommended_index_columns()
        meta = self._inspect_table_indexes()
        indexes = meta.get("indexes", {}) or {}
        leading_indexed = {cols[0] for cols in indexes.values() if cols}
        any_indexed = {c for cols in indexes.values() for c in cols}

        missing_leading = [c for c in recommendations if c not in leading_indexed]
        missing_any = [c for c in recommendations if c not in any_indexed]

        return {
            "driver": meta.get("driver"),
            "table": meta.get("table"),
            "schema": meta.get("schema"),
            "recommended_columns": recommendations,
            "indexed_columns_any_position": sorted(any_indexed),
            "indexed_columns_leading": sorted(leading_indexed),
            "missing_leading_indexes": missing_leading,
            "missing_any_indexes": missing_any,
            "contains_search_warning": str(getattr(self, "search_mode", "contains")).lower() == "contains",
        }

    def set_as_sub_resource_table(self):
        self.sub_resource_table = True
        return self

    def set_key_id(self, key_id: str):
        self.key_id = key_id
        return self

    def has_default_actions(self) -> bool:
        """Override this method to disable default actions column."""
        return True

    def has_custom_actions(self) -> bool:
        """
        Override to explicitly enable/disable custom actions.

        Default behavior: if get_custom_actions returns a non-empty list for a dummy record,
        we treat actions as present.
        """
        try:
            sample = {}
            actions = self.get_custom_actions(sample)
            return bool(actions)
        except Exception:
            return False

    def get_custom_actions(self, record) -> list[Action]:
        """Override this method to provide custom actions."""
        return []

    def has_header_actions(self) -> bool:
        """Override to enable header-level actions."""
        try:
            return bool(self.get_header_actions())
        except Exception:
            return False

    def get_header_actions(self) -> list[Action]:
        """Override to return header-level actions (e.g., Create, Export)."""
        return []

    def has_bulk_actions(self) -> bool:
        """Override to enable bulk actions (requires selectable=True)."""
        try:
            return bool(self.get_bulk_actions())
        except Exception:
            return False

    def get_bulk_actions(self) -> list[Action]:
        """Override to return bulk actions that receive selected row IDs."""
        return []

    def modify_table_query(self):
        """Override this method to modify the query for the table."""
        pass


class Table(
    TableBase,
    TableFiltersMixin,
    TableSearchSortMixin,
    TablePaginationMixin,
    TableExportMixin,
    TableRenderMixin,
):
    pass
