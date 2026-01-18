from framework1.core_services.Request import Request
from framework1.database.QueryBuilder import QueryBuilder
from framework1.dsl.TableFilter import Filter


class TableFiltersMixin:
    def apply_filter_conditions(self, query, filters: list[dict]):
        """
        Applies a list of filter dictionaries to the query, handling AND/OR and nesting.
        """

        def apply_group(q):
            for idx, cond in enumerate(filters):
                field = cond["field"]
                op = cond["operator"]
                val = cond.get("value", "")
                boolean = cond.get("boolean", "and").lower()
                values = [v.strip() for v in val.split(",")] if val else []

                # Determine AND vs OR application
                method = q.where if boolean == "and" or idx == 0 else q.or_where

                # Map operators to QueryBuilder methods
                match op:
                    case "where":
                        q = method(field, val)
                    case "not_equal":
                        q = method(field, "!=", val)
                    case "contains":
                        q = method(field, "LIKE", f"%{val}%")
                    case "starts_with":
                        q = method(field, "LIKE", f"{val}%")
                    case "ends_with":
                        q = method(field, "LIKE", f"%{val}")
                    case "greater_than":
                        q = method(field, ">", val)
                    case "less_than":
                        q = method(field, "<", val)
                    case "greater_than_eq":
                        q = method(field, ">=", val)
                    case "less_than_eq":
                        q = method(field, "<=", val)
                    case "in" if values:
                        q = method(field, "IN", values)
                    case "not_in" if values:
                        q = method(field, "NOT IN", values)
                    case "between" if len(values) == 2:
                        # Support both where_between_dates and or_where_between_dates
                        between_method_name = f"{method.__name__}_between_dates"
                        if hasattr(q, between_method_name):
                            q = getattr(q, between_method_name)(field, *values)
                    case "is_null":
                        q = method(field, "IS", None)
                    case "is_not_null":
                        q = method(field, "IS NOT", None)
                    case "regex":
                        q = method(field, "REGEXP", val)

            return q

        # If multiple filters in the same group, nest them for proper grouping
        return query.nest(apply_group) if len(filters) > 1 and hasattr(query, "nest") else apply_group(query)

    def _apply_filters_grouped(self, filters: list[Filter], query: QueryBuilder) -> QueryBuilder:
        request = Request()
        session = request.session()

        grouped: dict[str, list[Filter]] = {}
        ungrouped: list[Filter] = []

        # 1. Separate grouped and ungrouped filters
        for f in filters:
            group_key = getattr(f, "_group_key", None)
            if group_key:
                grouped.setdefault(group_key, []).append(f)
            else:
                ungrouped.append(f)

        # 2. Apply grouped filters using or_where
        for group_filters in grouped.values():
            for i, f in enumerate(group_filters):
                value = request.input(f"filter_" + f._key)
                if self.persist_filters:
                    value = value or session.get(f"{f._key}_filter")

                if value or (value is None and getattr(f, "_default_checked", False)):
                    if f._query_callback:
                        if i == 0:
                            query = f._query_callback(query)
                        else:
                            # TODO: grouped OR callbacks assume where; needs explicit handling
                            pass

        # 3. Apply ungrouped filters
        for f in ungrouped:
            query = f.apply(query, self.persist_filters)

        return query

    def filters(self) -> list[Filter]:
        """
        Override this in your table subclass to provide filters.
        Example: return [Filter.make("active").label("Active").query(lambda q: q.where_active())]
        """
        return []
