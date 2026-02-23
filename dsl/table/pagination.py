from framework1.core_services.Request import Request
from framework1.database.ActiveRecord import PaginationResult, SimplePaginationResult
from framework1.database.QueryBuilder import QueryBuilder


class CursorPaginationResult:
    def __init__(
        self,
        items,
        per_page: int,
        has_next: bool,
        next_cursor,
        current_cursor,
        cursor_param: str = "cursor",
    ):
        self.items = items
        self.total = None
        self.per_page = per_page
        self.current_page = 1
        self.last_page = 1
        self.has_next = has_next
        self.has_prev = current_cursor not in (None, "")
        self.next_cursor = next_cursor
        self.current_cursor = current_cursor
        self.cursor_param = cursor_param
        self.mode = "keyset"


class TablePaginationMixin:
    def _resolve_pagination_fallback_order_column(self) -> str:
        primary = str(getattr(self.query.__class__, "__primary_key__", "") or "id")
        # If primary key is alias-qualified (e.g. Ownership.BusinessPartyId),
        # use its leaf column and qualify against base table for MSSQL safety.
        leaf = primary.split(".")[-1] if "." in primary else primary
        table_name = str(getattr(self.query, "__table__", "") or "")
        return f"{table_name}.{leaf}" if table_name else leaf

    def paginate(self, page: int = None, per_page: int = None):
        """Use database-level pagination."""
        if not self.model:
            raise ValueError("Model class must be set to use pagination")

        request = Request()
        table_name = self.__class__.__name__
        instance_table = request.grouped(table_name)

        if str(getattr(self, "pagination_mode", "offset")).lower() == "keyset":
            return self._paginate_keyset(request, table_name, instance_table, per_page)

        if instance_table:
            page = page or int(instance_table.get(table_name).get("page", 1))
            per_page = per_page or int(instance_table.get(table_name).get("per_page", 10))
        else:
            page = page or request.integer("page", 1)
            per_page = per_page or request.integer("per_page", 10)

        # Snapshot the pre-pagination query so export can reuse the same
        # filtered/sorted query builder without page-specific LIMIT/OFFSET.
        try:
            self._export_base_query = self.query.clone() if hasattr(self.query, "clone") else self.query
            if hasattr(self._export_base_query, "remove_limit"):
                self._export_base_query.remove_limit()
        except Exception:
            self._export_base_query = None

        # Use the query builder from the model for pagination
        if hasattr(self.query.__class__, "__primary_key__") or getattr(self.query.__class__, "__driver__") == "mssql":
            if not self.query.order_by_clauses:
                fallback_order_column = self._resolve_pagination_fallback_order_column()
                self.pagination = self.query.order_by(fallback_order_column, "asc").paginate(
                    page, per_page, count_total=not getattr(self, "simple_paginate", False)
                )
            else:
                self.pagination = self.query.paginate(
                    page, per_page, count_total=not getattr(self, "simple_paginate", False)
                )
        else:
            self.pagination = self.query.paginate(
                page, per_page, count_total=not getattr(self, "simple_paginate", False)
            )

        if not isinstance(self.pagination, (PaginationResult, SimplePaginationResult)):
            self.pagination = {}
            self.data = []
            return self
        if not getattr(self, "dto_target", None):
            self.data = self.pagination.items.to_list_dict()
        else:
            self.data = self.pagination.items if not self.as_dto else self.pagination.items.to_dtos(self.dto_target)
        return self

    def _paginate_keyset(self, request: Request, table_name: str, instance_table, per_page: int = None):
        from framework1.database.active_record.utils.ModelCollection import ModelCollection

        if not hasattr(self.query, "all"):
            # Keyset mode currently targets ActiveRecord-style queries.
            self.pagination_mode = "offset"
            return self.paginate(per_page=per_page)

        table_state = instance_table.get(table_name, {}) if instance_table else {}
        per_page = per_page or int(table_state.get("per_page", request.integer("per_page", 10)))
        cursor_param = str(getattr(self, "keyset_param", "cursor") or "cursor")
        cursor = table_state.get(cursor_param, request.input(f"{table_name}[{cursor_param}]"))

        column = getattr(self, "keyset_column", None) or self._resolve_pagination_fallback_order_column()
        direction = str(getattr(self, "keyset_direction", "asc") or "asc").lower()
        if direction not in ("asc", "desc"):
            direction = "asc"

        if not self.query.order_by_clauses:
            self.query = self.query.order_by(column, direction)

        if cursor not in (None, ""):
            operator = ">" if direction == "asc" else "<"
            self.query = self.query.where(column, operator, cursor)

        self.query = self.query.limit(per_page + 1)
        rows = self.query.all()

        has_next = len(rows) > per_page
        items = ModelCollection(rows[:per_page])

        next_cursor = None
        if has_next and items:
            key_name = str(column).split(".")[-1]
            next_cursor = getattr(items[-1], key_name, None)

        self.pagination = CursorPaginationResult(
            items=items,
            per_page=per_page,
            has_next=has_next,
            next_cursor=next_cursor,
            current_cursor=cursor,
            cursor_param=cursor_param,
        )

        if not getattr(self, "dto_target", None):
            self.data = items.to_list_dict()
        else:
            self.data = items if not self.as_dto else items.to_dtos(self.dto_target)

        return self
