from framework1.core_services.Request import Request
from framework1.database.QueryBuilder import QueryBuilder
from framework1.dsl.TableFilter import Filter


class TableFiltersMixin:
    STRING_OPS = {
        "where", "not_equal", "contains", "starts_with", "ends_with",
        "in", "not_in", "is_null", "is_not_null"
    }
    NUMBER_OPS = {
        "where", "not_equal", "greater_than", "less_than", "greater_than_eq",
        "less_than_eq", "between", "in", "not_in", "is_null", "is_not_null"
    }
    DATE_OPS = {
        "where", "greater_than", "less_than", "greater_than_eq",
        "less_than_eq", "between", "is_null", "is_not_null"
    }
    FIELD_TYPE_OPS = {
        "string": STRING_OPS,
        "text": STRING_OPS,
        "number": NUMBER_OPS,
        "numeric": NUMBER_OPS,
        "integer": NUMBER_OPS,
        "float": NUMBER_OPS,
        "date": DATE_OPS,
        "datetime": DATE_OPS,
        "timestamp": DATE_OPS,
    }

    def _ensure_filter_runtime_cache(self):
        if getattr(self, "_filter_runtime_cache_ready", False):
            return
        self._filter_field_meta = getattr(self, "_filter_field_meta", {}) or {}
        self._filterable_leaf_set = {
            f.split(".")[-1] for f in (getattr(self, "filterable_fields", []) or [])
        }
        self._filter_runtime_cache_ready = True

    def _field_type(self, field: str) -> str:
        self._ensure_filter_runtime_cache()
        meta = getattr(self, "_filter_field_meta", {}) or {}
        return (meta.get(field, {}) or {}).get("type", "string")

    def _operator_allowed(self, field: str, operator: str) -> bool:
        field_type = self._field_type(field)
        ops_for_type = self.FIELD_TYPE_OPS.get(field_type, self.STRING_OPS | self.NUMBER_OPS | self.DATE_OPS)
        return operator in ops_for_type

    def apply_filter_conditions(self, query, filters: list[dict]):
        """
        Applies a list of filter dictionaries to the query, handling AND/OR and nesting.
        """
        self._ensure_filter_runtime_cache()
        allowed_leafs = getattr(self, "_filterable_leaf_set", set())

        def apply_group(q):
            for idx, cond in enumerate(filters):
                field = cond["field"]
                op = cond["operator"]
                val = cond.get("value", "")
                boolean = cond.get("boolean", "and").lower()
                values = [v.strip() for v in val.split(",")] if val else []

                # Guard: only allow whitelisted fields and operators
                if allowed_leafs and field.split(".")[-1] not in allowed_leafs:
                    continue
                if not self._operator_allowed(field, op):
                    continue

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
        self._ensure_filter_runtime_cache()
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

        grouped_keys = {f._key for group in grouped.values() for f in group}
        request_values = {key: request.input(f"filter_{key}") for key in grouped_keys}
        session_values = {}
        if self.persist_filters:
            session_values = {key: session.get(f"{key}_filter") for key in grouped_keys}

        # 2. Apply grouped filters using or_where
        for group_filters in grouped.values():
            def _apply_callback(target_query: QueryBuilder, callback):
                result = callback(target_query)
                return result if result is not None else target_query

            for i, f in enumerate(group_filters):
                value = request_values.get(f._key)
                if self.persist_filters:
                    value = value or session_values.get(f._key)

                if value or (value is None and getattr(f, "_default_checked", False)):
                    if f._query_callback:
                        if i == 0:
                            query = _apply_callback(query, f._query_callback)
                        else:
                            if hasattr(query, "or_nest"):
                                query = query.or_nest(lambda nested_q: _apply_callback(nested_q, f._query_callback))
                            else:
                                query = _apply_callback(query, f._query_callback)

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
