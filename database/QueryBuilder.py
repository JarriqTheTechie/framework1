import pprint
import re
import sys
from datetime import date, datetime
from typing import Any, List, Union, Tuple, Callable


class Raw:
    def __init__(self, expression: str):
        self.expression = expression

    def __str__(self):
        return self.expression


class DebugBreak(Exception):
    """Raised to simulate dd() behavior for debugging without exiting the process."""
    pass


def is_active_record_or_active_record_query(obj: Any) -> bool:
    from framework1.database.ActiveRecord import ActiveRecord
    return isinstance(obj, QueryBuilder) or isinstance(obj, ActiveRecord)


class QueryBuilder:
    __database__ = None

    __table__ = __name__

    def __init__(self):
        self.__driver__ = None
        self.__primary_key__ = getattr(self, "__primary_key__", "id")

        self.order_by_clauses: List[Tuple[str, str]] = []
        self.conditions = []
        self.having_conditions: List[Tuple[str, str]] = []
        self.rows_fetch = None
        self.ctes = []
        self.columns = ['*']
        self.group_by_columns: List[str] = []
        self.joins = []
        self.order_by_clause = None
        self.limit_count = None
        self.offset_count = None
        self.parameters: List[Any] = []
        self.distinct_flag = False
        self.alias = None
        self.unions: List[str] = []

    def _quote_column(self, col: str) -> str:
        if self.__driver__ == "mysql":
            return f"`{col}`"
        elif self.__driver__ == "mssql":
            return f"[{col}]"
        return col

    def remove_where(self, column: str, operator: str = None, value: Any = None):
        def normalize(expr: str) -> str:
            return expr.strip().lower().replace("  ", " ")

        # Build target pattern
        if operator and value is None:
            # e.g. column IS NULL → match "deleted_at IS NULL"
            target = f"{column} {operator} NULL"
        elif operator:
            target = f"{column} {operator} %s"
        else:
            target = column

        target = normalize(target)

        new_conditions = []
        for logic, expr in self.conditions:
            if normalize(expr) != target:
                new_conditions.append((logic, expr))

        self.conditions = new_conditions
        return self

    def remove_ordering(self):
        self.order_by_clause = None
        return self

    def clone(self) -> "QueryBuilder":
        """
        Creates a deep clone of the current query builder instance,
        preserving the structure and parameters, without modifying the original.
        """
        cloned = self.__class__()

        # Basic attributes
        cloned.__driver__ = self.__driver__
        cloned.__table__ = self.__table__
        cloned.__primary_key__ = self.__primary_key__

        # Copy lists
        cloned.columns = self.columns[:]
        cloned.conditions = self.conditions[:]
        cloned.parameters = self.parameters[:]
        cloned.order_by_clauses = self.order_by_clauses[:]
        cloned.having_conditions = self.having_conditions[:]
        cloned.group_by_columns = self.group_by_columns[:]
        cloned.joins = self.joins[:]
        cloned.ctes = self.ctes[:]
        cloned.unions = self.unions[:]

        # Copy values
        cloned.alias = self.alias
        cloned.limit_count = self.limit_count
        cloned.offset_count = self.offset_count
        cloned.rows_fetch = self.rows_fetch
        cloned.distinct_flag = self.distinct_flag
        return cloned

    def clone_without_columns_or_ordering(self) -> "QueryBuilder":
        """
        Creates a deep clone of the current query builder instance,
        preserving the structure and parameters, without modifying the original.
        """
        cloned = self.__class__()

        # Basic attributes
        cloned.__driver__ = self.__driver__
        cloned.__table__ = self.__table__
        cloned.__primary_key__ = self.__primary_key__

        # Copy lists
        cloned.conditions = self.conditions[:]
        cloned.parameters = self.parameters[:]
        cloned.having_conditions = self.having_conditions[:]
        cloned.group_by_columns = self.group_by_columns[:]
        cloned.joins = self.joins[:]
        cloned.ctes = self.ctes[:]
        cloned.unions = self.unions[:]

        # Copy values
        cloned.alias = self.alias
        cloned.limit_count = self.limit_count
        cloned.offset_count = self.offset_count
        cloned.rows_fetch = self.rows_fetch
        cloned.distinct_flag = self.distinct_flag
        return cloned

    def table(self, table_name: str, alias: str = None):
        self.__table__ = table_name
        if alias:
            self.alias = alias
        return self

    def set_driver(self, driver: str):
        if driver not in ["mysql", "mssql"]:
            raise ValueError("Unsupported driver. Supported drivers are 'mysql' and 'mssql'.")
        self.__driver__ = driver
        return self

    def select(self, *columns):
        self.columns = []
        if isinstance(columns[0], list):
            columns = columns[0]

        for col in columns:
            if isinstance(col, tuple):
                if isinstance(col[0], Raw):
                    self.columns.append(f"{col[0].expression} AS {col[1]}")
                else:
                    self.columns.append(f"{col[0]} AS {col[1]}")
            else:
                self.columns.append(str(col))

        return self

    def add_select(self, *columns):
        if isinstance(columns[0], list):
            columns = columns[0]

        for col in columns:
            if isinstance(col, tuple):
                if isinstance(col[0], Raw):
                    self.columns.append(f"{col[0].expression} AS {col[1]}")
                else:
                    self.columns.append(f"{col[0]} AS {col[1]}")
            else:
                self.columns.append(str(col))

        return self

    def add_select_subquery(self, subquery: 'QueryBuilder', alias: str):
        sub_sql = subquery.to_sql(include_select=True)
        self.columns.append(f"({sub_sql}) AS {alias}")
        self.parameters.extend(subquery.parameters)
        return self

    def when(self,
             condition: Any,
             callback: Callable[['QueryBuilder', Any], Any],
             default: Callable[['QueryBuilder', Any], Any] = None):
        if condition:
            callback(self, condition)
        elif default:
            default(self, condition)
        return self

    def unless(self, condition, if_true: Callable, default: Callable = None):
        if condition:
            return if_true(self, condition)
        elif default:
            return default(self, condition)
        return self

    def where(self, column, operator="=", value=None):
        if value is None and operator not in ["=", "!=", "<", "<=", ">", ">=", "<>", "LIKE", "IN", "IS", "IS NOT"]:
            value = operator
            operator = "="

        if isinstance(column, dict):
            # Handle dictionary input for where conditions
            for col, val in column.items():
                self.where(col, "=", val)
            return self

        if not isinstance(column, Raw):
            if isinstance(value, QueryBuilder):
                subquery = f"({value.to_sql()})"
                self.parameters.extend(value.parameters)
                self.conditions.append(('AND', f"{column} {operator} {subquery}"))


            elif isinstance(value, Raw):
                self.conditions.append(('AND', f"{column} {operator} {value.expression}"))


            elif isinstance(column, QueryBuilder):

                nested_query = f"({column.to_sql(False)})"
                self.parameters.extend(column.parameters)
                self.conditions.append(('AND', nested_query))
            else:
                placeholder = "%s"
                self.conditions.append(('AND', f"{column} {operator} {placeholder}"))
                self.parameters.append(value)
        else:
            if value is None:
                self.conditions.append(('AND', column.expression))
            elif isinstance(value, Raw):
                self.conditions.append(('AND', f"{column.expression} {operator} {value.expression}"))
            else:
                self.conditions.append(('AND', f"{column.expression} {operator} %s"))
                self.parameters.append(value)
        return self

    def or_where(self, column, operator=None, value=None):
        if value is None and operator not in ["=", "!=", "<", "<=", ">", ">=", "<>", "LIKE", "IN", "IS", "IS NOT"]:
            value = operator
            operator = "="

        if not isinstance(column, Raw):
            # Case: column is a nested ActiveRecordQB instance (e.g. .or_where(nested_query))
            if isinstance(column, QueryBuilder):
                nested_query = f"({column.to_sql(False)})"
                self.parameters.extend(column.parameters)
                self.conditions.append(('OR', nested_query))

            # Case: value is a subquery (e.g. .or_where("id", "IN", subquery))
            elif isinstance(value, QueryBuilder):
                subquery = f"({value.to_sql()})"
                self.parameters.extend(value.parameters)
                self.conditions.append(('OR', f"{column} {operator} {subquery}"))

            # Case: value is a raw SQL expression (e.g. .or_where("x", "=", Raw("NOW()")))
            elif isinstance(value, Raw):
                self.conditions.append(('OR', f"{column} {operator} {value.expression}"))

            # Case: regular condition (e.g. .or_where("status", "=", "Pending"))
            else:
                placeholder = "%s"
                self.conditions.append(('OR', f"{column} {operator} {placeholder}"))
                self.parameters.append(value)
        else:
            if value is None:
                self.conditions.append(('OR', column.expression))
            elif isinstance(value, Raw):
                self.conditions.append(('OR', f"{column.expression} {operator} {value.expression}"))
            else:
                self.conditions.append(('OR', f"{column.expression} {operator} %s"))
                self.parameters.append(value)

        return self

    def where_between(self, column, start, end):
        if isinstance(start, Raw) and isinstance(end, Raw):
            self.conditions.append(("AND", f"{column} BETWEEN {start.expression} AND {end.expression}"))
        elif isinstance(start, Raw):
            self.conditions.append(("AND", f"{column} BETWEEN {start.expression} AND %s"))
            self.parameters.append(end)
        elif isinstance(end, Raw):
            self.conditions.append(("AND", f"{column} BETWEEN %s AND {end.expression}"))
            self.parameters.append(start)
        else:
            self.conditions.append(("AND", f"{column} BETWEEN %s AND %s"))
            self.parameters.extend([start, end])
        return self

    def or_where_between(self, column, start, end):
        if isinstance(start, Raw) and isinstance(end, Raw):
            self.conditions.append(("OR", f"{column} BETWEEN {start.expression} AND {end.expression}"))
        elif isinstance(start, Raw):
            self.conditions.append(("OR", f"{column} BETWEEN {start.expression} AND %s"))
            self.parameters.append(end)
        elif isinstance(end, Raw):
            self.conditions.append(("OR", f"{column} BETWEEN %s AND {end.expression}"))
            self.parameters.append(start)
        else:
            self.conditions.append(("OR", f"{column} BETWEEN %s AND %s"))
            self.parameters.extend([start, end])
        return self

    def where_in(self, column, values):
        if isinstance(values, (list, tuple)):
            placeholders = ", ".join(["%s"] * len(values))
            self.conditions.append(("AND", f"{column} IN ({placeholders})"))
            self.parameters.extend(values)
        elif isinstance(values, QueryBuilder):
            subquery = f"({values.to_sql()})"
            self.conditions.append(("AND", f"{column} IN {subquery}"))
            self.parameters.extend(values.parameters)
        elif isinstance(values, Raw):
            self.conditions.append(("AND", f"{column} IN ({values.expression})"))
        return self

    def or_where_in(self, column, values):
        if isinstance(values, (list, tuple)):
            placeholders = ", ".join(["%s"] * len(values))
            self.conditions.append(("OR", f"{column} IN ({placeholders})"))
            self.parameters.extend(values)
        elif isinstance(values, QueryBuilder):
            subquery = f"({values.to_sql()})"
            self.conditions.append(("OR", f"{column} IN {subquery}"))
            self.parameters.extend(values.parameters)
        elif isinstance(values, Raw):
            self.conditions.append(("OR", f"{column} IN ({values.expression})"))
        return self

    def where_not_in(self, column, values):
        if isinstance(values, (list, tuple)):
            placeholders = ", ".join(["%s"] * len(values))
            self.conditions.append(("AND", f"{column} NOT IN ({placeholders})"))
            self.parameters.extend(values)
        elif isinstance(values, QueryBuilder):
            subquery = f"({values.to_sql()})"
            self.conditions.append(("AND", f"{column} NOT IN {subquery}"))
            self.parameters.extend(values.parameters)
        elif isinstance(values, Raw):
            self.conditions.append(("AND", f"{column} NOT IN ({values.expression})"))
        return self

    def or_where_not_in(self, column, values):
        if isinstance(values, (list, tuple)):
            placeholders = ", ".join(["%s"] * len(values))
            self.conditions.append(("OR", f"{column} NOT IN ({placeholders})"))
            self.parameters.extend(values)
        elif isinstance(values, QueryBuilder):
            subquery = f"({values.to_sql()})"
            self.conditions.append(("OR", f"{column} NOT IN {subquery}"))
            self.parameters.extend(values.parameters)
        elif isinstance(values, Raw):
            self.conditions.append(("OR", f"{column} NOT IN ({values.expression})"))
        return self

    def where_null(self, column):
        self.conditions.append(("AND", f"{column} IS NULL"))
        return self

    def or_where_null(self, column):
        self.conditions.append(("OR", f"{column} IS NULL"))
        return self

    def where_not_null(self, column):
        self.conditions.append(("AND", f"{column} IS NOT NULL"))
        return self

    def or_where_not_null(self, column):
        self.conditions.append(("OR", f"{column} IS NOT NULL"))
        return self

    def where_between_dates(self, column: str, start: Union[str, date, Raw], end: Union[str, date, Raw]):
        def normalize_date(val):
            if isinstance(val, Raw):
                return val
            if isinstance(val, (datetime, date)):
                return val.strftime("%Y-%m-%d")
            return str(val)

        start = normalize_date(start)
        end = normalize_date(end)

        return self.where_between(column, start, end)

    def where_any_columns(self, columns: List[str], operator: str, value: Any):
        return self.nest(lambda q: [q.or_where(col, operator, value) for col in columns])

    def or_where_any_columns(self, columns: List[str], operator: str, value: Any):
        return self.or_nest(lambda q: [q.or_where(col, operator, value) for col in columns])

    def where_all_columns(self, columns: List[str], operator: str, value: Any):
        return self.nest(lambda q: [q.where(col, operator, value) for col in columns])

    def or_where_all_columns(self, columns: List[str], operator: str, value: Any):
        return self.or_nest(lambda q: [q.where(col, operator, value) for col in columns])

    def where_none(self, columns: List[str]):
        return self.nest(lambda q: [q.where_null(col) for col in columns])

    def or_where_none(self, columns: List[str]):
        return self.or_nest(lambda q: [q.where_null(col) for col in columns])

    def where_like(self, column: str, pattern: str, case_sensitive: bool = False):
        if case_sensitive:
            return self.where(Raw(f"{column} COLLATE Latin1_General_CS_AS LIKE '{pattern}'"))
        return self.where(column, "LIKE", pattern)

    def or_where_like(self, column: str, pattern: str, case_sensitive: bool = False):
        if case_sensitive:
            return self.or_where(Raw(f"{column} COLLATE Latin1_General_CS_AS LIKE '{pattern}'"))
        return self.or_where(column, "LIKE", pattern)

    def where_not_like(self, column: str, pattern: str, case_sensitive: bool = False):
        if case_sensitive:
            return self.where(Raw(f"{column} COLLATE Latin1_General_CS_AS NOT LIKE '{pattern}'"))
        return self.where(column, "NOT LIKE", pattern)

    def or_where_not_like(self, column: str, pattern: str, case_sensitive: bool = False):
        if case_sensitive:
            return self.or_where(Raw(f"{column} COLLATE Latin1_General_CS_AS NOT LIKE '{pattern}'"))
        return self.or_where(column, "NOT LIKE", pattern)

    def where_date(self, column: str, operator: Union[str, date] = "=", value: Union[date, str, Raw] = None):
        if value is None:
            value = operator
            operator = "="
        self.conditions.append(("AND", f"CAST({column} AS DATE) {operator} %s"))
        self.parameters.append(value)
        return self

    def or_where_date(self, column: str, operator: Union[str, date] = "=", value: Union[date, str, Raw] = None):
        if value is None:
            value = operator
            operator = "="
        self.conditions.append(("OR", f"CAST({column} AS DATE) {operator} %s"))
        self.parameters.append(value)
        return self

    def where_month(self, column: str, value: str):
        return self.where(Raw(f"MONTH({column})"), "=", value)

    def or_where_month(self, column: str, value: str):
        return self.or_where(Raw(f"MONTH({column})"), "=", value)

    def where_day(self, column: str, value: str):
        return self.where(Raw(f"DAY({column})"), "=", value)

    def or_where_day(self, column: str, value: str):
        return self.or_where(Raw(f"DAY({column})"), "=", value)

    def where_year(self, column: str, value: str):
        return self.where(Raw(f"YEAR({column})"), "=", value)

    def or_where_year(self, column: str, value: str):
        return self.or_where(Raw(f"YEAR({column})"), "=", value)

    def where_time(self, column: str, value: str):
        return self.where(Raw(f"CAST({column} AS TIME)"), "=", value)

    def or_where_time(self, column: str, value: str):
        return self.or_where(Raw(f"CAST({column} AS TIME)"), "=", value)

    def where_today(self, column: str):
        return self.where_date(column, date.today())

    def where_past(self, column: str):
        return self.where_date(column, "<", date.today())

    def where_future(self, column: str):
        return self.where_date(column, ">", date.today())

    def where_before_today(self, column: str):
        return self.where_date(column, "<", date.today())

    def where_after_today(self, column: str):
        return self.where_date(column, ">", date.today())

    def where_column(self, column1: str, operator: str, column2: str):
        self.conditions.append(("AND", f"{column1} {operator} {column2}"))
        return self

    def or_where_column(self, column1: str, operator: str, column2: str):
        self.conditions.append(("OR", f"{column1} {operator} {column2}"))
        return self

    def where_full_text(self, column: str, value: str, mode: str = None):
        if self.__driver__ == "mysql":
            clause = f"MATCH({column}) AGAINST (%s"
            if mode:
                clause += f" IN {mode.upper()}"
            clause += ")"
            self.conditions.append(("AND", clause))
            self.parameters.append(value)
        elif self.__driver__ == "mssql":
            clause = f"CONTAINS({column}, %s)"
            self.conditions.append(("AND", clause))
            self.parameters.append(value)
        else:
            raise NotImplementedError("Full-text search not supported for this database.")
        return self

    def or_where_full_text(self, column: str, value: str, mode: str = None):
        if self.__driver__ == "mysql":
            clause = f"MATCH({column}) AGAINST (%s"
            if mode:
                clause += f" IN {mode.upper()}"
            clause += ")"
            self.conditions.append(("OR", clause))
            self.parameters.append(value)
        elif self.__driver__ == "mssql":
            clause = f"CONTAINS({column}, %s)"
            self.conditions.append(("OR", clause))
            self.parameters.append(value)
        else:
            raise NotImplementedError("Full-text search not supported for this database.")
        return self

    def nest(self, callback):
        subquery = QueryBuilder()
        callback(subquery)
        condition_sql = subquery._build_conditions(nested=True)
        if condition_sql:
            self.conditions.append(("AND", f"({condition_sql})"))
            self.parameters.extend(subquery.parameters)
        return self

    def or_nest(self, callback):
        subquery = QueryBuilder()
        callback(subquery)
        condition_sql = subquery._build_conditions(nested=True)
        if condition_sql:
            self.conditions.append(("OR", f"({condition_sql})"))
            self.parameters.extend(subquery.parameters)
        return self

    def order_by(self, column, direction="asc"):
        if column:
            direction = (direction or "").upper()
            if direction not in ("ASC", "DESC", ""):
                raise ValueError("Direction must be 'ASC', 'DESC', or ''")

            key = column.expression if isinstance(column, Raw) else str(column)

            # check only the first element of each tuple
            for i, (col, _) in enumerate(self.order_by_clauses):
                if col == key:
                    # update existing entry’s direction
                    self.order_by_clauses[i] = (col, direction)
                    break
            else:
                # not found → add it
                self.order_by_clauses.append((key, direction))
        else:
            self.remove_ordering()

        return self

    def latest(self, column: str = "id"):
        return self.order_by(column, "DESC")

    def oldest(self, column: str = "id"):
        return self.order_by(column, "ASC")

    def in_random_order(self):
        if self.__driver__ == "mssql":
            return self.order_by_raw("NEWID()")
        else:  # Default to MySQL/PostgreSQL-compatible
            return self.order_by_raw("RAND()")

    def limit(self, count):
        if self.__driver__ == "mssql":
            self.rows_fetch = "%s" if not isinstance(count, Raw) else count.expression
            if not isinstance(count, Raw):
                self.parameters.append(count)
        else:
            if isinstance(count, Raw):
                self.limit_count = count.expression
            else:
                self.limit_count = "%s"
                self.parameters.append(count)
        return self

    def remove_limit(self):
        """
        Remove both LIMIT and OFFSET constraints from the query.
        """
        self.rows_fetch = None
        self.limit_count = None
        self.offset_count = None  # Add this line to clear offset
        return self

    def as_count(self, column: str = "*", alias: str = "aggregate"):
        """
        Transform the current query into a COUNT query.

        - Preserves WHERE / JOIN / CTE / UNION logic
        - Removes ORDER BY, LIMIT, OFFSET
        - Wraps GROUP BY queries in a subquery
        - Returns self for chaining
        """

        # Clear pagination
        self.limit_count = None
        self.offset_count = None
        self.rows_fetch = None
        self.order_by_clauses = []

        # GROUP BY requires subquery wrapping
        if self.group_by_columns:
            sub = self.clone()
            sub.columns = ["1"]
            sub.order_by_clauses = []
            sub.limit_count = None
            sub.offset_count = None
            sub.rows_fetch = None

            # Reset this builder into a wrapper query
            self.columns = [Raw(f"COUNT(*) AS {alias}")]
            self.joins = []
            self.conditions = []
            self.group_by_columns = []
            self.having_conditions = []
            self.distinct_flag = False
            self.unions = []
            self.ctes = []

            self.__table__ = f"({sub.to_sql()}) AS count_subquery"
            self.parameters = sub.parameters[:]
            return self

        # Normal COUNT
        if self.distinct_flag and column != "*":
            self.columns = [Raw(f"COUNT(DISTINCT {column}) AS {alias}")]
        else:
            self.columns = [Raw(f"COUNT({column}) AS {alias}")]

        self.distinct_flag = False
        return self

    def offset(self, count):
        if self.__driver__ == "mssql":
            self.offset_count = "%s" if not isinstance(count, Raw) else count.expression
            if not isinstance(count, Raw):
                self.parameters.append(count)
        else:
            if isinstance(count, Raw):
                self.offset_count = count.expression
            else:
                self.offset_count = "%s"
                self.parameters.append(count)
        return self

    def fetch(self, count):
        self.rows_fetch = count
        return self

    def join(self, table, column1, operator, column2, join_type="INNER"):
        if f"{join_type} JOIN {table} ON {column1} {operator} {column2}" not in self.joins:
            self.joins.append(f"{join_type} JOIN {table} ON {column1} {operator} {column2}")
        return self

    def join_raw(self, table, raw_condition, join_type="INNER"):
        self.joins.append(f"{join_type} JOIN {table} ON {raw_condition}")
        return self

    def left_join(self, table, column1, operator, column2):
        return self.join(table, column1, operator, column2, join_type="LEFT")

    def right_join(self, table, column1, operator, column2):
        return self.join(table, column1, operator, column2, join_type="RIGHT")

    def full_join(self, table, column1, operator, column2):
        return self.join(table, column1, operator, column2, join_type="FULL OUTER")

    def cross_join(self, table):
        self.joins.append(f"CROSS JOIN {table}")
        return self

    def group_by(self, *columns: Union[str, Raw, List[Union[str, Raw]]]):
        if len(columns) == 1 and isinstance(columns[0], list):
            columns = columns[0]
        for col in columns:
            if isinstance(col, Raw):
                self.group_by_columns.append(col.expression)
            else:
                self.group_by_columns.append(col)
        return self

    def having(self, column, operator=None, value=None):
        if isinstance(column, Raw) and operator is None:
            self.having_conditions.append(('AND', column.expression))
        elif isinstance(value, Raw):
            self.having_conditions.append(('AND', f"{column} {operator} {value.expression}"))
        else:
            self.having_conditions.append(('AND', f"{column} {operator} %s"))
            self.parameters.append(value)
        return self

    def or_having(self, column, operator=None, value=None):
        if isinstance(column, Raw) and operator is None:
            self.having_conditions.append(('OR', column.expression))
        elif isinstance(value, Raw):
            self.having_conditions.append(('OR', f"{column} {operator} {value.expression}"))
        else:
            self.having_conditions.append(('OR', f"{column} {operator} %s"))
            self.parameters.append(value)
        return self

    def select_raw(self, raw_sql: str):
        self.columns = [Raw(raw_sql)]
        return self

    def where_raw(self, raw_sql: str):
        return self.where(Raw(raw_sql))

    def or_where_raw(self, raw_sql: str):
        return self.or_where(Raw(raw_sql))

    def having_raw(self, raw_sql: str):
        return self.having(Raw(raw_sql))

    def or_having_raw(self, raw_sql: str):
        return self.or_having(Raw(raw_sql))

    def order_by_raw(self, raw_sql: str):
        direction = ""
        return self.order_by(Raw(raw_sql), direction)

    def group_by_raw(self, raw_sql: str):
        return self.group_by(Raw(raw_sql))

    def distinct(self):
        self.distinct_flag = True
        return self

    def where_exists(self, subquery: 'QueryBuilder'):
        sql = f"EXISTS ({subquery.to_sql()})"
        self.conditions.append(("AND", sql))
        self.parameters.extend(subquery.parameters)
        return self

    def where_not_exists(self, subquery: 'QueryBuilder'):
        sql = f"NOT EXISTS ({subquery.to_sql()})"
        self.conditions.append(("AND", sql))
        self.parameters.extend(subquery.parameters)
        return self

    def where_any(self, callback: Callable[['QueryBuilder'], None]):
        nested = QueryBuilder()
        callback(nested)
        sql = nested._build_conditions(nested=True)
        if sql:
            self.conditions.append(('AND', f'({sql})'))
            self.parameters.extend(nested.parameters)
        return self

    def case(self, cases: List[Tuple[str, Any]], else_result: Any, alias: str):
        parts = [f"WHEN {condition} THEN %s" for condition, _ in cases]
        self.parameters.extend([val for _, val in cases])
        self.parameters.append(else_result)
        sql = f"CASE {' '.join(parts)} ELSE %s END AS {alias}"
        self.columns.append(Raw(sql))
        return self

    def lateral_join(self, subquery: 'QueryBuilder', alias: str, on_clause: str):
        sql = f"LEFT JOIN LATERAL ({subquery.to_sql()}) AS {alias} ON {on_clause}"
        self.parameters.extend(subquery.parameters)
        self.joins.append(sql)
        return self

    def union(self, subquery: 'QueryBuilder'):
        self.unions.append(f"UNION {subquery.to_sql()}")
        self.parameters.extend(subquery.parameters)
        return self

    def union_all(self, subquery: 'QueryBuilder'):
        self.unions.append(f"UNION ALL {subquery.to_sql()}")
        self.parameters.extend(subquery.parameters)
        return self

    def paginate(self, page: int, per_page: int = 10):
        """Apply pagination to the query.

        Args:
            page (int): Page number to retrieve
            per_page (int): Number of items per page
        """
        if page < 1 or per_page < 1:
            raise ValueError("Page and per_page must be >= 1")

        # Reset previous pagination
        self.limit_count = None
        self.offset_count = None
        self.rows_fetch = None
        if not hasattr(self, "_pagination_params"):
            self._pagination_params = []
        # Remove previously injected pagination params by identity, not value
        for p in getattr(self, "_pagination_params", []):
            try:
                self.parameters.remove(p)
            except ValueError:
                pass
        self._pagination_params = []

        offset = (page - 1) * per_page

        if self.__driver__ == "mssql":
            # MSSQL requires an ORDER BY for OFFSET/FETCH
            if not self.order_by_clauses:
                raise ValueError("MSSQL requires ORDER BY clause for pagination.")
            self.offset_count = "%s"
            self.parameters.append(offset)
            self._pagination_params.append(offset)

            self.rows_fetch = "%s"
            self.parameters.append(per_page)
            self._pagination_params.append(per_page)
        else:
            self.limit_count = "%s"
            self.parameters.append(per_page)
            self._pagination_params.append(per_page)

            self.offset_count = "%s"
            self.parameters.append(offset)
            self._pagination_params.append(offset)

        return self

    def with_cte(self, name: str, query: 'QueryBuilder'):
        """
        Adds a Common Table Expression (CTE) to the query.

        :param name: The name of the CTE.
        :param query: An instance of ActiveRecordQB whose SQL will define the CTE.
        :return: Self (for chaining).
        """
        sub_sql = query.to_sql(include_select=True)
        self.ctes.append(f"{name} AS ({sub_sql})")
        self.parameters.extend(query.parameters)
        return self

    def insert(self, data: dict[str, Any], has_triggers=False):
        """
        Generates a cross-compatible INSERT INTO SQL statement.

        :param data: Dict of column-value pairs.
        :return: (SQL string, parameter list)
        """
        if not data:
            raise ValueError("No data provided for insert.")

        columns = ", ".join(self._quote_column(col) for col in data.keys())

        # Handle Raw() values properly
        placeholders = []
        params = []

        for value in data.values():
            if isinstance(value, Raw):
                placeholders.append(value.expression)  # literal SQL expression
            else:
                # Use the correct placeholder style for driver
                placeholders.append("?" if self.__driver__ == "mssql" else "%s")
                params.append(value)

        placeholders_str = ", ".join(placeholders)

        if self.__driver__ == "mysql":
            sql = f"INSERT INTO {self.__table__} ({columns}) VALUES ({placeholders_str})"
        else:  # mssql
            sql = f"INSERT INTO {self.__table__} ({columns}) OUTPUT INSERTED.* VALUES ({placeholders_str})"

        if has_triggers:
            sql = sql.replace("OUTPUT INSERTED.*", "")

        pprint.pp(sql)
        return sql, params

    def insert_get_id(self, data: dict[str, Any]):
        if not data:
            raise ValueError("No data provided to insert_get_id.")

        columns = ", ".join(self._quote_column(col) for col in data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        values = list(data.values())

        if self.__driver__ == "mysql":
            sql = f"INSERT INTO {self.__table__} ({columns}) VALUES ({placeholders}); SELECT LAST_INSERT_ID();"
        elif self.__driver__ == "mssql":
            sql = f"INSERT INTO {self.__table__} ({columns}) VALUES ({placeholders}); SELECT SCOPE_IDENTITY();"
        else:
            raise NotImplementedError("insert_get_id not supported for this database.")

        return sql, values

    def insert_many(self, rows: List[dict[str, Any]], ignore=False):
        """
        Generate a bulk INSERT statement for MySQL, or a single-row template for MSSQL (to be used with executemany).
        Returns (sql, params, use_executemany).
        """
        if not rows:
            raise ValueError("No rows provided for bulk insert.")

        keys = list(rows[0].keys())
        for row in rows:
            if set(row.keys()) != set(keys):
                raise ValueError("All rows must have the same keys.")

        columns = ", ".join(self._quote_column(k) for k in keys)

        driver = getattr(self, "__driver__", "mysql")

        if driver == "mssql":
            # MSSQL: single-row insert template, params are list of tuples
            placeholder = "(" + ", ".join(["?"] * len(keys)) + ")"
            sql = f"INSERT INTO {self.__table__} ({columns}) VALUES {placeholder}"
            params = [tuple(row.values()) for row in rows]
            return sql, params, True  # True = executemany mode

        else:
            # MySQL: multi-row VALUES with %s
            placeholder = "(" + ", ".join(["%s"] * len(keys)) + ")"
            values_clause = ", ".join([placeholder] * len(rows))
            match ignore:
                case True:
                    sql = f"INSERT IGNORE INTO {self.__table__} ({columns}) VALUES {values_clause}"
                case _:
                    sql = f"INSERT INTO {self.__table__} ({columns}) VALUES {values_clause}"

            params = [value for row in rows for value in row.values()]
            return sql, params, False  # False = single execute

    def insert_or_ignore(self, rows: list[dict[str, Any]]):
        if not rows:
            raise ValueError("No rows provided for insert_or_ignore")

        keys = list(rows[0].keys())
        quoted_cols = ", ".join(self._quote_column(k) for k in keys)

        params = []

        if self.__driver__ == "mysql":
            placeholders = ", ".join(["%s"] * len(keys))
            all_placeholders = ", ".join([f"({placeholders})"] * len(rows))
            sql = f"INSERT IGNORE INTO {self.__table__} ({quoted_cols}) VALUES {all_placeholders}"
            for row in rows:
                params.extend(row.values())

        elif self.__driver__ == "mssql":
            insert_clauses = []
            for row in rows:
                cond = " AND ".join(f"{self._quote_column(k)} = %s" for k in row.keys())
                insert = (
                    f"IF NOT EXISTS (SELECT 1 FROM {self.__table__} WHERE {cond})\n"
                    f"    INSERT INTO {self.__table__} ({quoted_cols}) VALUES ({', '.join(['%s'] * len(keys))});"
                )
                insert_clauses.append(insert)
                params.extend(row.values())  # for WHERE
                params.extend(row.values())  # for INSERT
            sql = "\n".join(insert_clauses)

        else:
            raise NotImplementedError(f"insert_or_ignore is not implemented for driver {self.__driver__}")

        return sql.strip(), params

    def insert_using(self, columns: list[str], subquery: 'QueryBuilder'):
        if not columns or not isinstance(subquery, QueryBuilder):
            raise ValueError("insert_using requires a list of columns and a valid subquery.")

        quoted_cols = ", ".join(self._quote_column(col) for col in columns)
        sub_sql = subquery.to_sql(include_select=True)
        params = subquery.get_parameters()

        sql = f"INSERT INTO {self.__table__} ({quoted_cols}) {sub_sql}"
        return sql.strip(), params

    def update(self, values: dict[str, Any]):
        # self.guard(values=values)
        if hasattr(self, '__builder__'):
            builder = self.__builder__
            if not builder:
                builder = self
        else:
            builder = self

        if not values:
            raise ValueError("No update values provided.")

        set_clause = ", ".join(f"{builder._quote_column(k)} = %s" for k in values)
        set_params = list(values.values())

        where_clause = builder._build_conditions(nested=False)
        if not where_clause:
            raise ValueError("Unsafe update: missing WHERE clause.")

        sql = f"UPDATE {builder.__table__} SET {set_clause} {where_clause.strip()}"

        all_params = set_params + builder.parameters
        return sql.strip(), all_params

    def upsert(self, rows: list[dict[str, Any]], unique_by: list[str], update_columns: list[str]):
        if not rows:
            raise ValueError("No data provided for upsert.")

        all_columns = list(rows[0].keys())
        placeholders = "(" + ", ".join(["%s"] * len(all_columns)) + ")"
        values_clause = ", ".join([placeholders] * len(rows))
        values = [val for row in rows for val in row.values()]

        if self.__driver__ == "mysql":
            updates = ", ".join([f"`{col}` = VALUES(`{col}`)" for col in update_columns])
            sql = (
                f"INSERT INTO {self.__table__} ({', '.join(f'`{c}`' for c in all_columns)}) "
                f"VALUES {values_clause} ON DUPLICATE KEY UPDATE {updates}"
            )

        elif self.__driver__ == "mssql":
            source_alias = "src"
            target_alias = "target"

            # Build MERGE statement for MSSQL
            on_clause = " AND ".join(
                [f"{target_alias}.[{col}] = {source_alias}.[{col}]" for col in unique_by]
            )

            update_clause = ", ".join(
                [f"{target_alias}.[{col}] = {source_alias}.[{col}]" for col in update_columns]
            )

            insert_columns = ", ".join(f"[{col}]" for col in all_columns)
            insert_values = ", ".join(f"{source_alias}.[{col}]" for col in all_columns)

            values_rows = ", ".join(
                "(" + ", ".join(["%s"] * len(all_columns)) + ")" for _ in rows
            )
            values = [val for row in rows for val in row.values()]

            sql = (
                f"MERGE INTO {self.__table__} AS {target_alias} "
                f"USING (VALUES {values_rows}) AS {source_alias} ({', '.join(f'[{c}]' for c in all_columns)}) "
                f"ON {on_clause} "
                f"WHEN MATCHED THEN UPDATE SET {update_clause} "
                f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values});"
            )

        else:
            raise NotImplementedError("Upsert is not implemented for this database.")

        return sql.strip(), values

    def update_or_insert(self, match_conditions: dict[str, Any], update_values: dict[str, Any]):
        combined_row = {**match_conditions, **update_values}
        unique_by = list(match_conditions.keys())
        update_columns = list(update_values.keys())
        return self.upsert([combined_row], unique_by=unique_by, update_columns=update_columns)

    def increment(self, column: str, amount: int = 1):
        sql = f"UPDATE {self.__table__} SET {column} = {column} + %s"
        where_clause = self._build_conditions()
        sql += f" {where_clause}"
        params = [amount] + self.parameters
        return sql, params

    def decrement(self, column: str, amount: int = 1):
        sql = f"UPDATE {self.__table__} SET {column} = {column} - %s"
        where_clause = self._build_conditions()
        sql += f" {where_clause}"
        params = [amount] + self.parameters
        return sql, params

    def increment_each(self, pairs: dict[str, int]):
        set_clause = ", ".join([f"{col} = {col} + %s" for col in pairs])
        sql = f"UPDATE {self.__table__} SET {set_clause}"
        where_clause = self._build_conditions()
        sql += f" {where_clause}"
        params = list(pairs.values()) + self.parameters
        return sql, params

    def decrement_each(self, pairs: dict[str, int]):
        set_clause = ", ".join([f"{col} = {col} - %s" for col in pairs])
        sql = f"UPDATE {self.__table__} SET {set_clause}"
        where_clause = self._build_conditions()
        sql += f" {where_clause}"
        params = list(pairs.values()) + self.parameters
        return sql, params

    def delete(self):
        sql = f"DELETE FROM {self.__table__}"
        where_clause = self._build_conditions()
        sql += f" {where_clause}"
        return sql.strip(), self.parameters

    def substitute_params(self, sql: str, params: list[Any]):
        for param in params:
            if isinstance(param, str):
                value = f"'{param}'"
            elif param is None:
                value = "NULL"
            else:
                value = str(param)
            sql = sql.replace("%s", value, 1)
        return sql

    def dump(self):
        sql, params = self.get()
        print("[DUMP] SQL:", sql)
        print("[DUMP] Params:", params)
        return self

    def dd(self):
        sql, params = self.get()
        print("[DD] SQL:", sql)
        print("[DD] Params:", params)
        raise DebugBreak({
            "message": "[DD] Debugging SQL",
            "sql": sql,
            "params": params,
        })

    def dd_raw_sql(self):
        sql, params = self.get()
        print("[DD RAW SQL]:", self.substitute_params(sql, params))
        raise DebugBreak(f"[DD RAW SQL]: {self.substitute_params(sql, params)}")

    def dump_raw_sql(self):
        sql, params = self.get()
        print("[DUMP RAW SQL]:", self.substitute_params(sql, params))
        return self

    def to_raw_sql(self):
        sql, params = self.get()
        return self.substitute_params(sql, params)

    def _build_joins(self):
        return " ".join(self.joins) if self.joins else ""

    def _build_conditions(self, nested=False):
        if not self.conditions:
            return ""
        conditions = []
        for condition in self.conditions:
            conditions.append(f"{condition[0]} {condition[1]}")

        result = " ".join(conditions)
        if not nested:
            if result.startswith("AND "):
                result = result[4:]  # Remove leading "AND "
            elif result.startswith("OR "):
                result = result[3:]  # Remove leading "OR "
            return " WHERE " + result

        return re.sub(r"^(AND |OR )", "", result)

    def to_sql(self, include_select=True):
        if hasattr(self, "__scopes_enabled__") and self.__scopes_enabled__:
            self.apply_scopes()

        sql = ""

        if self.ctes:
            sql += f"WITH {', '.join(self.ctes)} "

        if include_select:
            if self.distinct_flag:
                sql += "SELECT DISTINCT "
            else:
                sql += "SELECT "

            sql += f"{', '.join(str(c) for c in self.columns)} FROM {self.__table__}"
            if self.alias:
                sql += f" AS {self.alias}"

        sql += " " + self._build_joins()
        sql += self._build_conditions(nested=not include_select)

        if self.group_by_columns and include_select:
            sql += f" GROUP BY {', '.join(str(g) for g in self.group_by_columns)}"

        if self.having_conditions and include_select:
            having_clause = " ".join(f"{logic} {cond}" for logic, cond in self.having_conditions)
            having_clause = having_clause.lstrip("AND ").lstrip("OR ")
            sql += f" HAVING {having_clause}"

        if self.order_by_clauses and include_select:
            order_by_str = ", ".join(f"{str(col)} {dir}" for col, dir in self.order_by_clauses)
            sql += f" ORDER BY {order_by_str}"

        if self.limit_count is not None and include_select:
            sql += f" LIMIT {self.limit_count}"

        if self.rows_fetch:
            sql += f" OFFSET {self.offset_count or 0} ROWS FETCH NEXT {self.rows_fetch} ROWS ONLY"

        if not self.rows_fetch:
            if self.offset_count is not None and include_select:
                sql += f" OFFSET {self.offset_count}"

        for union_sql in self.unions:
            sql += f" {union_sql}"

        return sql.strip()

    def get(self):
        return self.to_sql(), self.parameters

    def get_parameters(self):
        return self.parameters

    def guard(self, values: dict[str, Any] = None):
        if isinstance(self, QueryBuilder) and not self.__table__:
            raise ValueError("No table specified for update operation.")
        if not values or not isinstance(values, dict):
            raise ValueError("Update values must be a non-empty dictionary.")
        if not self.__table__:
            raise ValueError("No table specified for update operation.")
        if not self.__driver__:
            raise ValueError("No driver specified for update operation.")
        if self.__driver__ not in ["mysql", "mssql"]:
            raise NotImplementedError("Update is not implemented for this database driver.")
        if not isinstance(values, dict):
            raise ValueError("Update values must be a dictionary.")
