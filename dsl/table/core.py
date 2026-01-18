from argparse import Action

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

    persist_sort = False
    persist_search = False
    persist_filters = False
    selectable = False
    master_detail_expandable = True

    filterable_fields = []

    search_placeholder = "Search..."

    def __init__(self, data: list[dict] = None, non_activerecord_model=None, as_dto=False, dto_target=None):
        self.pagination = None
        self.data = data
        self.query = None
        self.sub_resource_table = False
        self.table_name = self.__class__.__name__

        # If a model is set, initialize its query builder
        try:
            self.query = self.model() if self.model else None
        except TypeError:
            self.query = self.model if self.model else None

        # If user overrides modify_table_query, apply it
        if self.modify_table_query.__func__ is not TableBase.modify_table_query:
            # Step 1: Get normalized filters from the form
            filters = Request().grouped("filters")
            grouped_filters = {}

            # Step 2: Group filters by "group"
            for f in filters:
                group_name = f.get("group", "default") or "default"
                grouped_filters.setdefault(group_name, []).append(f)

            # Step 3: Apply each group of filters to the query
            for _, group_filters in grouped_filters.items():
                self.query = self.apply_filter_conditions(self.query, group_filters)
            self.query = self.modify_table_query()
        else:
            # Step 1: Get normalized filters from the form
            filters = Request().grouped("filters")
            grouped_filters = {}

            # Step 2: Group filters by "group"
            for f in filters:
                group_name = f.get("group", "default") or "default"
                grouped_filters.setdefault(group_name, []).append(f)

            # Step 3: Apply each group of filters to the query
            for _, group_filters in grouped_filters.items():
                self.query = self.apply_filter_conditions(self.query, group_filters)

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

        # If user supplied static data
        if self.data is None and self.query is not None:
            # Load all records (if no pagination is used yet)
            self.data = self.query.get()

        # If user wants DTOs
        if as_dto and self.model and dto_target:
            self.as_dto = as_dto
            self.dto_target = dto_target

    def schema(self):
        """Override this method to define schema."""
        return []

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
        """Override this method to enable custom actions column."""
        return False

    def get_custom_actions(self, record) -> list[Action]:
        """Override this method to provide custom actions."""
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
