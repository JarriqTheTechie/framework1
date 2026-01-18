from framework1.core_services.Request import Request
from framework1.database.ActiveRecord import PaginationResult
from framework1.database.QueryBuilder import QueryBuilder


class TablePaginationMixin:
    def paginate(self, page: int = None, per_page: int = None):
        """Use database-level pagination."""
        if not self.model:
            raise ValueError("Model class must be set to use pagination")

        request = Request()
        table_name = self.__class__.__name__
        instance_table = request.grouped(table_name)
        print(instance_table)

        if instance_table:
            page = page or int(instance_table.get(table_name).get("page", 1))
            per_page = per_page or int(instance_table.get(table_name).get("per_page", 10))
        else:
            page = page or request.integer("page", 1)
            per_page = per_page or request.integer("per_page", 10)

        # Use the query builder from the model for pagination
        if hasattr(self.query.__class__, "__primary_key__") or getattr(self.query.__class__, "__driver__") == "mssql":
            if not self.query.order_by_clauses:
                self.pagination = self.query.order_by(self.query.__class__.__primary_key__, "asc").paginate(
                    page, per_page
                )
            else:
                self.pagination = self.query.paginate(page, per_page)
        else:
            self.pagination = self.query.paginate(page, per_page)

        if not isinstance(self.pagination, PaginationResult):
            self.pagination = {}
            self.data = []
            return self
        if not getattr(self, "dto_target", None):
            self.data = self.pagination.items.to_list_dict()
        else:
            self.data = self.pagination.items if not self.as_dto else self.pagination.items.to_dtos(self.dto_target)
        return self
