import json
import pprint
import time
from _collections_abc import Iterable

from framework1.core_services.MSSQLDatabase import result_to_dotdict, get_column_names
import inflect
import re
from copy import deepcopy
from datetime import datetime
from framework1.core_services.Database import Database
from framework1.database.BulkPreloader import BulkPreloader
from framework1.database.Events import Events
from framework1.database.active_record.utils.ModelCollection import ModelCollection
from framework1.database.fields.Fields import Field, JsonField, MSSQLJsonField
from framework1.utilities.DataKlass import DataKlass
from functools import wraps
from slugify import slugify
from typing import Any, TypeVar, Type, Optional, Self, List, NoReturn, override, Callable
from dotenv import load_dotenv
import inspect
from framework1.ddd.ValueObject import ValueObject
from operator import itemgetter
from logly import logger

load_dotenv()
p = inflect.engine()
T = TypeVar("T", bound="ActiveRecord")

from framework1.database.QueryBuilder import QueryBuilder, Raw, count_sql_placeholders
from framework1.database.schema_cache import get_table_columns_cached

from datetime import datetime, date


class dualmethod:
    def __init__(self, func: Callable[..., Any]):
        self.func = func

    def __get__(self, obj: Any, cls: Type[T]):
        """
        Handles:
            - class-bound call → clone class → call method
            - instance-bound call → call method normally
        """
        if obj is None:
            # Called from CLASS
            def wrapper(*args, **kwargs):
                # Auto-clone class before method runs
                new_cls = type(cls.__name__, cls.__bases__, dict(cls.__dict__))
                # Pass cloned class as first argument
                return self.func(new_cls, *args, **kwargs)

            return wrapper

        else:
            # Called from INSTANCE
            def wrapper(*args, **kwargs):
                return self.func(obj, *args, **kwargs)

            return wrapper


def get_model_fields(model_or_class):
    """
    Returns a dict of {field_name: FieldInstance} for all declared Field attributes.
    Works with both class and instance objects.
    """
    cls = model_or_class if isinstance(model_or_class, type) else model_or_class.__class__

    fields = {}
    for name, value in vars(cls).items():
        if isinstance(value, Field):
            fields[name] = value
    return fields


def normalize_values(record: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in record.items():
        if isinstance(v, str):
            try:
                # Try parsing YYYY-MM-DD
                out[k] = datetime.strptime(v, "%Y-%m-%d").date()
                continue
            except ValueError:
                pass
        out[k] = v
    return out


def dto(mapping: dict[str, str]):
    """
    Decorator for DTO mappers.
    - Auto maps fields from __data__ and relationships.
    - If DTO has ValueObject fields, wraps them automatically.
    """

    def decorator(fn):
        fn.__dto_mapping__ = mapping
        fn.__is_dto_mapper__ = True

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            target_name = fn.__name__.removeprefix("to_")
            mapped = {}

            for dto_field, model_field in mapping.items():
                if model_field in self.__data__:
                    mapped[dto_field] = self.__data__[model_field]
                    continue

                cache_attr = f"_{model_field}_cache"
                if hasattr(self, cache_attr):
                    related = getattr(self, cache_attr)
                    if isinstance(related, list):
                        mapped[dto_field] = [
                            r.to_dto(target_name) if hasattr(r, "to_dto") else r.to_dict()
                            for r in related
                        ]
                    elif related:
                        mapped[dto_field] = (
                            related.to_dto(target_name) if hasattr(related, "to_dto") else related.to_dict()
                        )
                    else:
                        mapped[dto_field] = None
                else:
                    mapped[dto_field] = None

            # --- AUTO-WRAP VALUE OBJECTS ---
            dto_cls = fn.__annotations__.get("return")  # get DTO class
            if dto_cls:
                hints = getattr(dto_cls, "__annotations__", {})
                for field, hint in hints.items():
                    if field in mapped and inspect.isclass(hint) and issubclass(hint, ValueObject):
                        if mapped[field] is not None and not isinstance(mapped[field], hint):
                            mapped[field] = hint(mapped[field])

            return fn(mapped, *args, **kwargs)

        return wrapper

    return decorator


def parse_withs(withs: list[str]) -> dict:
    """
    Turns ["client.alerts", "client.profile", "user.roles.permissions"]
    into:
    {
        "client": {"alerts": {}, "profile": {}},
        "user": {"roles": {"permissions": {}}}
    }
    """
    tree = {}
    for w in withs:
        parts = w.split(".")
        node = tree
        for p in parts:
            node = node.setdefault(p, {})
    return tree


def expand_withs(withs: list[str]) -> list[str]:
    expanded = set(withs)
    for w in withs:
        parts = w.split(".")
        for i in range(1, len(parts)):
            expanded.add(".".join(parts[:i]))
    return list(expanded)


class Relationship:
    def add_constraints(self, models: List["ActiveRecord"]):
        ...

    def match(self, results):
        ...


def mark_relationship(query, rel_type: str, owner_key: str = None, foreign_key: str = None,
                      foriegn_key_alias: str = None, local_key_alias: str = None):
    query.__is_relationship__ = True
    setattr(query, f"__{rel_type}__", True)
    query.__owner_key__ = owner_key
    query.__foreign_key__ = foreign_key
    query.__foreign_key_alias__ = foriegn_key_alias
    query.__owner_key_alias__ = local_key_alias
    return query


def split_camel_case(word: str) -> str:
    """Split PascalCase or camelCase into space-separated words."""
    return re.sub(r'(?<!^)(?=[A-Z])', ' ', word)


def to_pascal_case(phrase: str) -> str:
    return ''.join(word.capitalize() for word in phrase.split())


def to_snake_case(phrase: str) -> str:
    return '_'.join(word.lower() for word in phrase.split())


def transform_word(raw_word: str):
    spaced = split_camel_case(raw_word)  # e.g. "Destruction Log"
    plural_spaced = p.plural(spaced.lower())  # e.g. "Destruction Logs"

    return {
        "title_singular": spaced.title(),  # Destruction Log
        "title_plural": plural_spaced.title(),  # Destruction Logs
        "slug_singular": slugify(spaced),  # destruction-log
        "slug_plural": slugify(plural_spaced),  # destruction-logs
        "pascal_singular": to_pascal_case(spaced),  # DestructionLog
        "pascal_plural": to_pascal_case(plural_spaced),  # DestructionLogs
        "snake_singular": to_snake_case(spaced),  # destruction_log
        "snake_plural": to_snake_case(plural_spaced),  # destruction_logs
    }


def replace_select_fields(sql: str, new_fields: str) -> str:
    """
    Replace only the first occurrence of text between SELECT and FROM with a given string.
    """
    pattern = r"(?i)(SELECT\s+)(.*?)(\s+FROM\s+)"
    return re.sub(pattern, rf"\1{new_fields}\3", sql, count=1, flags=re.DOTALL)


class PaginationResult:
    def __init__(self, items, total, per_page, current_page):
        self.items = items
        self.total = total
        self.per_page = per_page
        self.current_page = current_page
        self.last_page = max((total + per_page - 1) // per_page, 1)

    @property
    def has_next(self): return self.current_page < self.last_page

    @property
    def has_prev(self): return self.current_page > 1

    def to_dict(self):
        return {
            "data": [item.to_dict() for item in self.items],
            "total": self.total,
            "per_page": self.per_page,
            "current_page": self.current_page,
            "last_page": self.last_page,
            "has_next": self.has_next,
            "has_prev": self.has_prev
        }


class SimplePaginationResult:
    def __init__(self, items, per_page, current_page, has_next: bool):
        self.items = items
        self.total = None
        self.per_page = per_page
        self.current_page = current_page
        self.last_page = current_page + (1 if has_next else 0)
        self._has_next = has_next
        self.mode = "simple"

    @property
    def has_next(self):
        return self._has_next

    @property
    def has_prev(self):
        return self.current_page > 1

    def to_dict(self):
        return {
            "data": [item.to_dict() for item in self.items],
            "total": self.total,
            "per_page": self.per_page,
            "current_page": self.current_page,
            "last_page": self.last_page,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
            "mode": self.mode,
        }


class ActiveRecordMeta(type):
    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)

        # Handle any @on(...) decorated functions
        for attr_name, attr_value in attrs.items():
            if hasattr(attr_value, "__event_name__"):
                event = attr_value.__event_name__
                priority = getattr(attr_value, "__event_priority__", 0)
                cls.on(event, attr_value, priority)

        if not attrs.get("__abstract__", False):
            cls.boot()


class ActiveRecord(QueryBuilder, Events,
                   metaclass=ActiveRecordMeta):
    __table__: str
    __primary_key__: str = None
    __database__: Type[Database] = Database
    __abstract__: bool = True
    __appends__: list[str] = []
    __timestamps_disabled__: bool = False
    # Projection optimization flags (can be overridden per model)
    __optimize_active_record_projection__: bool = True
    __optimize_preloader_projection__: bool = False
    # Projection overrides (optional, per model)
    # - include: if set, only these columns are eligible for auto-select
    # - exclude: columns removed from auto-select
    __projection_include__: list[str] | None = None
    __projection_exclude__: list[str] = []

    # ---------------------------------------------------------------------------
    # Class-level properties
    # ---------------------------------------------------------------------------

    def __init__(self, **kwargs: Any):
        super().__init__()
        self.__class__.boot()
        self.db: Database = self.__database__()
        self.__primary_key__ = self.get_primary_key_column()
        self.__data__: dict[str, Any] = {}
        self.__original__: dict[str, Any] = {}
        self.__builder__: Optional[QueryBuilder] = None
        self.__driver__ = getattr(self.__class__, '__driver__', None)
        # Initialize instance-specific relationship loading state
        self.__loading_relationships__ = False
        self.__pending_queries__ = {}
        self.__relationship_names__ = {}  # Add this line
        self.__find_called__ = False  # Track if find was called

        self.__scopes_enabled__ = True  # Enable scopes by default
        self.gather_scopes()
        self._with_events = False

        self.__timestamps_override__ = getattr(self, "__timestamps_override__", {
            "created_at": "created_at",
            "updated_at": "updated_at",
            "deleted_at": "deleted_at"
        })

        self.__timestamps_disabled__ = getattr(self, "__timestamps_disabled__", False)

        self.fill(**kwargs)

    def get_appends(self):
        """
        Returns the list of appended fields.
        """
        return self.__appends__

    @dualmethod
    def without_appends(self_or_cls: Self | Type[Self], appends: list[str] = None):
        """
        Remove specific appended attributes for this instance/class.
        - When `appends` is None, all appends are cleared.
        - When a list is provided, those names are subtracted from the current append set.
        """
        base = list(getattr(self_or_cls, "__appends__", []) or [])
        if appends is None:
            new_appends = []
        else:
            new_appends = [a for a in base if a not in appends]
        # dualmethod clones classes on class-call; scope changes to the clone/instance only.
        self_or_cls.__appends__ = new_appends
        return self_or_cls

    def __getattribute__(self, key) -> Any:
        """
        Intercepts attribute access only for defined model fields.
        Returns values from __data__ for fields defined on the class.
        """
        # Get the class first using super to avoid recursion
        cls = super().__getattribute__('__class__')

        # Check if this is a field defined on the class
        try:
            class_attr = super().__getattribute__(key)
            if isinstance(class_attr, Field):
                # If it's a field, return the value from __data__
                data = super().__getattribute__('__data__')
                return data.get(key)
        except AttributeError:
            pass

        # Normal attribute lookup for everything else
        return super().__getattribute__(key)

    def __getattr__(self, key):
        """
        Handles dynamic finders generation for attributes that don't exist
        """

        if key.startswith("where_in_"):
            field_name = key[9:]

            def dynamic_where_in(value):
                return self.where_in(field_name, value)

            return dynamic_where_in

        if key.startswith('or_where_in_'):
            field_name = key[12:]

            def dynamic_or_where_in(value):
                return self.or_where_in(field_name, value)

            return dynamic_or_where_in

        if key.startswith("where_null_"):
            field_name = key[11:]

            def dynamic_where_null():
                return self.where_null(field_name)

            return dynamic_where_null

        if key.startswith("where_not_null_"):
            field_name = key[16:]

            def dynamic_where_not_null():
                return self.where_not_null(field_name)

            return dynamic_where_not_null

        if key.startswith('where_'):
            field_name = key[6:]  # Remove 'where_' prefix

            def dynamic_where(value):
                return self.where(field_name, '=', value)

            return dynamic_where

        if key.startswith('or_where_'):
            field_name = key[9:]

            def dynamic_where(value):
                return self.or_where(field_name, '=', value)

            return dynamic_where

        if key.startswith('find_by_'):
            field_name = key[9:]

            def dynamic_find_by(value):
                return self.find_by(field_name, value)

            return dynamic_find_by

        try:
            # Try to access the attribute normally
            return super().__getattribute__(f"get_{key}_attribute")()
        except IndexError:
            pass

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}'")

    def fill(self, **kwargs: Any) -> Self:
        self.__data__.update(kwargs)
        self.__original__ = deepcopy(self.__data__)
        return self

    def refresh(self) -> Self:
        pk = self.get_primary_key_column()
        if pk not in self.__data__:
            raise ValueError("Cannot refresh a record without a primary key.")
        fresh = self.find(self.__data__[pk])
        if fresh:
            self.fill(**fresh.to_dict())
        return self

    def clone(self: T) -> T:
        """
        Clone query + ActiveRecord-specific runtime overrides.
        """
        new_instance = self.__class__()

        # Copy core QueryBuilder state.
        new_instance.__driver__ = self.__driver__
        new_instance.__table__ = self.__table__
        new_instance.__primary_key__ = self.__primary_key__
        new_instance.columns = self.columns[:]
        new_instance.conditions = self.conditions[:]
        new_instance.parameters = self.parameters[:]
        new_instance.order_by_clauses = self.order_by_clauses[:]
        new_instance.having_conditions = self.having_conditions[:]
        new_instance.group_by_columns = self.group_by_columns[:]
        new_instance.joins = self.joins[:]
        new_instance.ctes = self.ctes[:]
        new_instance.unions = self.unions[:]
        new_instance.alias = self.alias
        new_instance.limit_count = self.limit_count
        new_instance.offset_count = self.offset_count
        new_instance.rows_fetch = self.rows_fetch
        new_instance.distinct_flag = self.distinct_flag
        new_instance._pagination_param_count = getattr(self, "_pagination_param_count", 0)

        # Preserve runtime relation/appends overrides.
        if hasattr(self, "_with_overrides"):
            try:
                new_instance._with_overrides = list(getattr(self, "_with_overrides") or [])
            except Exception:
                new_instance._with_overrides = getattr(self, "_with_overrides")
        if hasattr(self, "__appends__"):
            try:
                new_instance.__appends__ = list(getattr(self, "__appends__") or [])
            except Exception:
                new_instance.__appends__ = getattr(self, "__appends__")

        # Preserve misc query execution flags used by read/query paths.
        for attr in (
            "__scopes_enabled__",
            "__projection_include__",
            "__projection_exclude__",
            "__optimize_active_record_projection__",
            "__preload_hint__",
        ):
            if hasattr(self, attr):
                setattr(new_instance, attr, getattr(self, attr))

        return new_instance

    def _apply_scopes_once_for_read(self):
        # Read paths call to_sql() later; applying scopes once here keeps
        # query shape stable and lets us safely inspect joins/projection.
        if getattr(self, "__scopes_enabled__", False):
            self.apply_scopes()
            self.__scopes_enabled__ = False
        return self

    def _apply_explicit_select_if_safe(self):
        """
        Replace implicit SELECT * with explicit model columns when safe.
        Keep SELECT * for joined queries or when fields are unavailable.
        """
        if not getattr(self, "__optimize_active_record_projection__", True):
            return self

        columns = getattr(self, "columns", None) or []
        if not (len(columns) == 1 and str(columns[0]).strip() == "*"):
            return self

        # Joins can change the projection shape; keep wildcard unless caller selected columns.
        if getattr(self, "joins", None):
            return self

        db_columns = self._get_db_table_columns_for_projection()
        if not db_columns:
            return self

        try:
            fields = [f for f in self.get_fields().keys() if f in set(db_columns)]
        except Exception:
            fields = []

        include = getattr(self, "__projection_include__", None)
        exclude = set(getattr(self, "__projection_exclude__", []) or [])
        if include:
            include_set = set(include)
            fields = [f for f in fields if f in include_set]
        if exclude:
            fields = [f for f in fields if f not in exclude]

        if fields:
            self.select(fields)
        return self

    def _get_db_table_columns_for_projection(self):
        return get_table_columns_cached(
            db=getattr(self, "db", None),
            driver=getattr(self, "__driver__", ""),
            table_raw=getattr(self, "__table__", ""),
        )

    def exists(self) -> bool:
        return bool(self.clone().select_raw("1").limit(1).db.query(*self.get()))

    def has_one(self, model, foreign_key: str = None, local_key: str = None) -> Self:
        from framework1.cli.resource_handler import transform_word

        # Parent primary key (local key by default)
        parent_primary_key = self.get_primary_key_column()
        local_key = local_key or parent_primary_key

        # Related model instance + table
        related_model = model()
        related_table = model.__table__

        # Guess foreign key if not provided: <parent_singular>_id
        if not foreign_key:
            foreign_key = f"{transform_word(self.__table__).get('snake_singular')}_id"

        query = related_model.where(
            f"{related_table}.{foreign_key}",  # related table's foreign key column
            getattr(self, local_key)  # parent local key value
        )
        return mark_relationship(query, "has_one", foreign_key=foreign_key, owner_key=local_key)

    def has_one_through(
            self,
            through,
            model,
            first_key: str,
            second_key: str,
            through_owner_key: str = None,
            target_owner_key: str = None,
    ):
        """
        Preloadable has_one_through relationship, via multi-step resolution.
        """
        query = model().new_query()
        query.__has_one_through__ = True
        query.__through__ = through
        query.__first_key__ = first_key
        query.__second_key__ = second_key
        query.__through_owner_key__ = through_owner_key or through().get_primary_key_column()
        query.__target_owner_key__ = target_owner_key or model().get_primary_key_column()

        return mark_relationship(query, "one", owner_key=query.__first_key__, foreign_key=query.__second_key__)

    def belongs_to(self, model, foreign_key: str = None, owner_key: str = None):
        related_model = model()
        related_table = model.__table__
        if not foreign_key and not owner_key:
            if hasattr(related_model, "__primary_key__"):
                foreign_key = related_model.__primary_key__
                owner_key = related_model.__primary_key__
            else:
                raise Exception(
                    f"Either foreign_key or owner_key must be provided for belongs_to relationship in {self.__class__.__name__}")

        # Guess foreign key if not provided
        if not foreign_key:
            foreign_key = f"{transform_word(related_table).get('snake_singular')}_id"

        # Default owner key = related PK
        owner_key = owner_key or related_model.get_primary_key_column()

        # Build query
        query = related_model.where(
            f"{related_table}.{owner_key}",
            getattr(self, foreign_key)
        )

        return mark_relationship(query, "belongs_to", foreign_key=foreign_key, owner_key=owner_key)

    def has_many(self, model, foreign_key: str = None, local_key: str = None, foriegn_key_alias: str = None,
                 local_key_alias: str = None) -> Self:
        from framework1.cli.resource_handler import transform_word

        parent_primary_key = self.get_primary_key_column()
        local_key = local_key or parent_primary_key

        related_model = model()
        related_table = model.__table__

        if not foreign_key:
            foreign_key = f"{transform_word(self.__table__).get('snake_singular')}_id"

        query = related_model.where(
            f"{related_table}.{foreign_key}",
            getattr(self, local_key)
        )

        return mark_relationship(query, "has_many", owner_key=local_key, foreign_key=foreign_key,
                                 foriegn_key_alias=foriegn_key_alias, local_key_alias=local_key_alias)

    def hybrid_many_relationship(self, query: Relationship) -> QueryBuilder:
        """
        Define a custom relationship using a pre-built query.
        You must specify the relationship type ('one' or 'many') and optionally
        the owner_key and foreign_key for proper relationship mapping.
        """
        query = query()
        query.db = getattr(query, "add_constraints")(self).__dict__.get("db")
        query.__constraints__ = getattr(query, "add_constraints")(self)
        query.__is_relationship__ = True
        query.__rel_type__ = "many"
        query.__match_fn__ = getattr(query, "match")
        return query

    def with_(self, withs: list[str]) -> "Self":
        """
        Merge additional relationships with defaults for this instance only.
        """
        base = getattr(self, "_with_overrides", None) or getattr(self, "__with__", [])
        self._with_overrides = expand_withs(base + withs)
        return self

    @dualmethod
    def with_only(self_or_cls: Self | Type[Self], withs: list[str]) -> Self:
        """
        Replace relationships entirely for this instance only.
        """
        normalized = expand_withs(withs)
        self_or_cls._with_overrides = normalized
        if isinstance(self_or_cls, type):
            self_or_cls.__with__ = []
        return self_or_cls

    def without(self_or_cls: Self | Type[Self], withouts: list[str]) -> Self:
        """
        Remove specific relationships from the preload set for this instance only.
        Public interface mirrors with_only.
        """
        base = getattr(self_or_cls, "_with_overrides", None) or getattr(self_or_cls, "__with__", [])
        remaining = [w for w in base if w not in withouts]
        normalized = expand_withs(remaining)
        self_or_cls._with_overrides = normalized
        if isinstance(self_or_cls, type):
            self_or_cls.__with__ = []
        return self_or_cls

    def preload_hint(self: T, strategy: str, **options: Any) -> T:
        """
        Optional relationship preload strategy hint for BulkPreloader.
        Supported strategies: in, chunked_in, exists_only, skip
        """
        strategy_name = str(strategy or "in").strip().lower()
        self.__preload_hint__ = {"strategy": strategy_name, **options}
        return self

    def _table_ref_for_exists(self, query_like, fallback_table: str) -> str:
        alias = str(getattr(query_like, "alias", "") or "").strip()
        return alias or fallback_table

    def _strip_relation_value_condition(self, subquery, related_col: str) -> None:
        """
        Remove the eager relation's concrete parent-value predicate (e.g. `child.fk = %s`)
        so it can be replaced by a correlated `where_column(...)`.
        """
        conditions = list(getattr(subquery, "conditions", []) or [])
        params = list(getattr(subquery, "parameters", []) or [])
        related_leaf = str(related_col).split(".")[-1]

        target_cond_idx = None
        target_param_start = 0
        target_param_count = 0
        param_cursor = 0

        for idx, (_logic, expr) in enumerate(conditions):
            expr_text = str(expr)
            ph = count_sql_placeholders(expr_text)
            if (
                target_cond_idx is None
                and ph > 0
                and "=" in expr_text
                and (related_col in expr_text or related_leaf in expr_text)
            ):
                target_cond_idx = idx
                target_param_start = param_cursor
                target_param_count = ph
                break
            param_cursor += ph

        if target_cond_idx is not None:
            conditions.pop(target_cond_idx)
            if target_param_count > 0:
                del params[target_param_start:target_param_start + target_param_count]
            subquery.conditions = conditions
            subquery.parameters = params

    def with_exists(
        self: T,
        relationships: str | list[str],
        aliases: dict[str, str] | None = None,
    ) -> T:
        """
        Project relationship existence booleans onto the current query.

        Example:
            Payment().with_exists(["latest_alert"]).all()
            # => each row has `latest_alert_exists` (0/1 or False/True by driver)
        """
        rels = [relationships] if isinstance(relationships, str) else list(relationships or [])
        aliases = aliases or {}
        parent_ref = self._table_ref_for_exists(self, self.get_table())

        for rel_name in rels:
            relation = getattr(self, rel_name, None)
            if not callable(relation):
                raise AttributeError(f"Unknown relationship '{rel_name}' on {self.__class__.__name__}.")

            rel_query = relation()
            if not getattr(rel_query, "__is_relationship__", False):
                raise ValueError(f"'{rel_name}' is not a preloadable relationship.")

            if getattr(rel_query, "__has_many__", False) or getattr(rel_query, "__has_one__", False):
                foreign_key = getattr(rel_query, "__foreign_key__", None)
                owner_key = getattr(rel_query, "__owner_key__", None)
                if not foreign_key or not owner_key:
                    raise ValueError(f"Relationship '{rel_name}' is missing key metadata.")

                related_ref = self._table_ref_for_exists(rel_query, rel_query.get_table())
                related_col = f"{related_ref}.{foreign_key}"
                parent_col = f"{parent_ref}.{owner_key}"
            elif getattr(rel_query, "__belongs_to__", False):
                foreign_key = getattr(rel_query, "__foreign_key__", None)
                owner_key = getattr(rel_query, "__owner_key__", None)
                if not foreign_key or not owner_key:
                    raise ValueError(f"Relationship '{rel_name}' is missing key metadata.")

                related_ref = self._table_ref_for_exists(rel_query, rel_query.get_table())
                related_col = f"{related_ref}.{owner_key}"
                parent_col = f"{parent_ref}.{foreign_key}"
            else:
                raise NotImplementedError(
                    f"with_exists currently supports has_one/has_many/belongs_to only ('{rel_name}')."
                )

            sub = rel_query.clone_without_columns_or_ordering()
            sub.select_raw("1")
            sub.remove_ordering()
            sub.remove_limit()
            self._strip_relation_value_condition(sub, related_col)
            sub.where_column(related_col, "=", parent_col)

            alias = aliases.get(rel_name, f"{rel_name}_exists")
            self.columns.append(
                f"CASE WHEN EXISTS ({sub.to_sql(include_select=True)}) THEN 1 ELSE 0 END AS {alias}"
            )
            # SELECT-subquery bindings must come before outer WHERE bindings.
            self.parameters = list(sub.parameters) + list(self.parameters)

        return self

    # ---------------------------------------------------------------------------
    # Debugging and introspection
    # ---------------------------------------------------------------------------

    def raw_sql(self) -> str:
        """
        Returns the raw SQL string with parameters substituted.
        """
        sql, params = self.get()
        return self.substitute_params(sql, params)

    def explain(self) -> list[dict[str, Any]]:
        """
        Returns the query execution plan.
        """
        sql, params = self.get()
        return self.db.query(f"EXPLAIN {sql}", *params)

    def tap(self, callback: callable) -> Self:
        """
        Taps into the query chain for debugging.

        Args:
            callback: Function to call with the query instance
        """
        callback(self)
        return self

    def dump_sql(self) -> Self:
        """
        Dumps the current SQL and continues the query chain.
        """
        sql, params = self.get()
        print("[SQL]", self.substitute_params(sql, params))
        return self

    def dd_sql(self) -> NoReturn:
        """
        Dumps the current SQL and stops execution.
        """
        print("[SQL]", self.raw_sql())
        sys.exit("[Execution stopped by .dd_sql()]")

    def debug(self) -> Self:
        """
        Logs the query for debugging.
        """
        sql, params = self.get()
        logger.debug(self.substitute_params(sql, params))
        return self

    def introspect_database_fields(self) -> list[dict[str, Any]]:
        """
        Introspect live database columns for this model's table (ignores declared Field attributes).
        Returns list of dicts: [{"name": ..., "type": ..., "nullable": ..., "default": ...}, ...]
        """
        def _row_value(row: Any, index: int, key: str) -> Any:
            try:
                return row[index]
            except (KeyError, IndexError, TypeError):
                if hasattr(row, "get"):
                    return row.get(key)
                return None

        table = self.get_table()
        driver = (self.__driver__ or "").lower()
        cursor = None

        try:
            cursor = self.db.connect()

            if driver == "mysql":
                schema = getattr(self.db, "connection_dict", {}).get("database")
                sql = (
                    "SELECT COLUMN_NAME AS name, DATA_TYPE AS type, "
                    "IS_NULLABLE AS nullable, COLUMN_DEFAULT AS default_value "
                    "FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_NAME = %s"
                )
                params = [table]
                if schema:
                    sql += " AND TABLE_SCHEMA = %s"
                    params.append(schema)
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return [
                    {
                        "name": _row_value(row, 0, "name"),
                        "type": _row_value(row, 1, "type"),
                        "nullable": _row_value(row, 2, "nullable"),
                        "default": _row_value(row, 3, "default_value"),
                    }
                    for row in rows
                ]

            if driver == "sqlite":
                cursor.execute(f"PRAGMA table_info({table})")
                rows = cursor.fetchall()
                return [
                    {
                        "name": row[1],
                        "type": row[2],
                        "nullable": row[3] == 0,
                        "default": row[4],
                    }
                    for row in rows
                ]

            # Default and MSSQL: use INFORMATION_SCHEMA
            sql = (
                "SELECT COLUMN_NAME AS name, DATA_TYPE AS type, "
                "IS_NULLABLE AS nullable, COLUMN_DEFAULT AS default_value "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = ?"
            )
            cursor.execute(sql, (table,))
            rows = cursor.fetchall()
            return [
                {
                    "name": _row_value(row, 0, "name"),
                    "type": _row_value(row, 1, "type"),
                    "nullable": _row_value(row, 2, "nullable"),
                    "default": _row_value(row, 3, "default_value"),
                }
                for row in rows
            ]

        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if hasattr(self.db, "_cleanup"):
                    self.db._cleanup()
            except Exception:
                pass

    # --------------------------------------------------------------------------
    # Basic Model Information
    # --------------------------------------------------------------------------

    def is_loaded(self) -> bool:
        return bool(self.__data__)

    def get_table(self) -> str:
        return getattr(self, "__table__", "")

    @dualmethod
    def get_primary_key_column(self) -> str:
        return getattr(self, "__primary_key__")

    # --------------------------------------------------------------------------
    # Query Creation
    # --------------------------------------------------------------------------

    def new_query(self: T) -> T:
        """
        Creates a new query instance with the same configuration as the current model.
        """
        query = self.__class__()
        if self.__driver__:
            query.set_driver(self.__driver__)
        return query

    def new(self, **kwargs: Any) -> T:
        """
        Create a new instance of the model with the given attributes.
        """
        instance = self.__class__(**kwargs)
        instance.__original__ = deepcopy(instance.__data__)
        return instance

    def new_with_builder(self: T, builder: QueryBuilder, **kwargs) -> T:
        """
        Create a new instance of the model with the given attributes and a pre-defined query builder.
        """
        instance = self.new(**kwargs)
        instance.__builder__ = builder
        instance.conditions = builder.conditions[:]
        instance.parameters = builder.parameters[:]
        return instance

    # --------------------------------------------------------------------------
    # Scopes
    # --------------------------------------------------------------------------

    def apply_scopes(self):
        """
        Apply the scope to the current query.
        This method should be overridden in subclasses to apply specific scopes.
        """
        for scope in self.__scopes__:
            scope[list(scope.keys())[0]](self)

    def get_scopes(self):
        """
        Get the list of scopes applied to the current query.
        """
        return self.__scopes__

    def without_scopes(self, excluded_scopes: list[str] | None = None) -> T:
        """
        Create a new instance of the model without any scopes applied.
        If specific scopes are provided, they will be excluded from the new instance.
        """
        if excluded_scopes is None:
            self.__scopes__ = []
            self.__scopes_enabled__ = False
            return self

        flattened_scopes = {k: v for d in self.__scopes__ for k, v in d.items()}
        for scope in excluded_scopes:
            if flattened_scopes.get(scope):
                del flattened_scopes[scope]

        unmerged = [{k: v} for k, v in flattened_scopes.items()]
        self.__scopes__ = unmerged
        return self

    def with_scopes(self, *scopes: str) -> T:
        """
        Create a new instance of the model with specific scopes applied.
        """
        self.__scopes__ = []
        self.__scopes_enabled__ = True
        for scope in scopes:
            if hasattr(self, scope):
                method = getattr(self, scope)
                if callable(method):
                    self.__scopes__.append(method)
        return self

    def gather_scopes(self):
        """
        Gather all scopes applied to the current query.
        This method is used to collect scopes for later use.
        """
        self.__scopes__ = []
        for base in self.__class__.__bases__:
            if base.__name__.endswith("Scope"):
                if hasattr(base, "apply"):
                    scope = {base.__qualname__: base.apply}
                    self.__scopes__.append(scope)
        return self.__scopes__

    # --------------------------------------------------------------------------
    # Change Tracking
    # --------------------------------------------------------------------------

    def was_changed(self, field: str) -> bool:
        """
        Check if a specific field was changed compared to the original state.
        """
        return self.__original__.get(field) != self.__data__.get(field)

    def get_changed_fields(self) -> list[str]:
        """
        Get a list of all fields that were changed.
        """
        return [
            key for key in self.__data__
            if self.__original__.get(key) != self.__data__.get(key)
        ]

    # --------------------------------------------------------------------------
    # Field Serialization Helpers
    # --------------------------------------------------------------------------

    def _serialize_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Coerce field values into driver-friendly representations.
        Currently used to JSON-encode MSSQLJsonField/JsonField values so pyodbc
        receives strings instead of dict/list objects.
        """
        fields = self.get_fields()
        serialized: dict[str, Any] = {}

        for key, value in data.items():
            field = fields.get(key)
            if isinstance(field, (JsonField, MSSQLJsonField)):
                if value is None:
                    serialized[key] = None
                    continue

                obj = value
                # Allow domain objects to expose serializable payloads
                if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
                    try:
                        obj = obj.to_dict()
                    except Exception:
                        pass

                # Tuples are not JSON-serializable by default
                if isinstance(obj, tuple):
                    obj = list(obj)

                if isinstance(obj, (dict, list)):
                    serialized[key] = json.dumps(obj, default=str)
                elif isinstance(obj, str):
                    serialized[key] = obj
                else:
                    serialized[key] = json.dumps(obj, default=str)
            else:
                serialized[key] = value

        return serialized

    # --------------------------------------------------------------------------
    # Schema Introspection
    # --------------------------------------------------------------------------

    @classmethod
    def get_fields(cls) -> dict[str, "Field"]:
        from framework1.database.fields.Fields import Field  # Import here to avoid cyclic issues
        fields = {}
        for name in dir(cls):
            attr = getattr(cls, name)
            if isinstance(attr, Field):
                fields[name] = attr
        return fields

    # --------------------------------------------------------------------------
    # Schema Generation
    # --------------------------------------------------------------------------

    @classmethod
    def _column_definition(cls, name: str, field: "Field", driver: str) -> tuple[str, bool]:
        """
        Build a column definition string for CREATE/ALTER statements.
        Returns (definition, is_primary_key).
        """
        driver = driver.lower()
        if driver == "mssql":
            col_def = f"[{name}] {field.get_sql_type()}"
        else:
            col_def = f"`{name}` {field.get_sql_type()}"

        if getattr(field, "auto_increment", False):
            if driver == "mssql":
                col_def += " IDENTITY(1,1)"
            else:
                col_def += " AUTO_INCREMENT"

        if field.collation:
            col_def += f" COLLATE {field.collation}"
        if not field.nullable:
            col_def += " NOT NULL"
        if field.unique:
            col_def += " UNIQUE"

        default = getattr(field, "default", None)
        if default is not None:
            if isinstance(default, Raw):
                col_def += f" DEFAULT {default.expression}"
            elif isinstance(default, str):
                default_upper = default.upper()
                if default_upper in ("CURRENT_TIMESTAMP", "NOW()", "GETDATE()"):
                    col_def += f" DEFAULT {default}"
                else:
                    col_def += f" DEFAULT '{default}'"
            elif isinstance(default, (int, float)):
                col_def += f" DEFAULT {default}"

        if field.comment:
            if driver == "mysql":
                col_def += f" COMMENT '{field.comment}'"
            else:
                col_def += f" -- {field.comment}"

        return col_def, getattr(field, "primary_key", False)

    @classmethod
    def generate_schema(cls) -> str:
        fields = cls.get_fields()
        if not fields:
            raise ValueError(f"{cls.__name__} has no declared fields.")

        columns = []
        pk = None
        driver = getattr(cls, "__driver__", "mysql").lower()

        for name, field in fields.items():
            col_def, is_pk = cls._column_definition(name, field, driver)
            if is_pk:
                pk = name

            columns.append(col_def)

        # Add primary key constraint
        if pk:
            if driver == "mssql":
                columns.append(f"CONSTRAINT PK_{cls.__table__}_{pk} PRIMARY KEY ([{pk}])")
            else:
                columns.append(f"PRIMARY KEY (`{pk}`)")

        table_name = getattr(cls, "__table__", cls.__name__)

        # MySQL syntax
        if driver == "mysql":
            return f"CREATE TABLE IF NOT EXISTS `{table_name}` (\n  " + ",\n  ".join(columns) + "\n);"

        # MSSQL syntax
        elif driver == "mssql":
            return (
                    f"IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{table_name}' AND xtype='U')\n"
                    f"BEGIN\n"
                    f"CREATE TABLE [{table_name}] (\n  " + ",\n  ".join(columns) + "\n);\nEND;"
            )

        else:
            raise ValueError(f"Unsupported driver '{driver}' for schema generation.")

    @classmethod
    def create_table(cls) -> None:
        sql = cls.generate_schema()
        db = cls.__database__()
        logger.debug(sql)
        cursor = db.connect()
        cursor.execute(sql)
        db.connection.commit()
        if hasattr(db, "_cleanup"):
            db._cleanup()
        cls.sync_table(db=db)
        logger.info(f"Table `{cls.__table__}` created.")

    @classmethod
    def sync_table(cls, db: Database | None = None) -> list[str]:
        """
        Ensure newly declared fields are present on the table via ALTER TABLE ADD COLUMN.
        Returns the executed ALTER statements.
        """
        model = cls()
        if db:
            model.db = db

        driver = getattr(cls, "__driver__", "mysql").lower()
        table_name = getattr(cls, "__table__", cls.__name__)

        existing = {col["name"].lower() for col in (model.introspect_database_fields() or [])}

        alters = []
        for name, field in cls.get_fields().items():
            if name.lower() in existing:
                continue
            if getattr(field, "primary_key", False):
                # Primary key additions are high risk; require manual migration.
                continue

            col_def, _ = cls._column_definition(name, field, driver)
            if driver == "mssql":
                alters.append(f"ALTER TABLE [{table_name}] ADD {col_def}")
            else:
                alters.append(f"ALTER TABLE `{table_name}` ADD COLUMN {col_def}")

        if alters:
            cursor = model.db.connect()
            for statement in alters:
                logger.debug(statement)
                cursor.execute(statement)
            model.db.connection.commit()
            if hasattr(model.db, "_cleanup"):
                model.db._cleanup()

        return alters

    # --------------------------------------------------------------------------
    # Migrations
    # --------------------------------------------------------------------------

    @classmethod
    def run_migrations(cls, migrations_dir: str = "migrations", direction: str = "up"):
        files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".py") and not f.startswith("__"))
        for file in files:
            path = os.path.join(migrations_dir, file)
            name = file[:-3]
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

    # --------------------------------------------------------------------------
    # Serialization
    # --------------------------------------------------------------------------

    def to_dict(self, instance=None) -> DataKlass:
        from framework1.database.ActiveRecord import ActiveRecord

        data = {}
        field_names = list(get_model_fields(self).keys())

        # Serialize stored DB fields
        for key, value in self.__data__.items():
            # if key not in field_names:
            #     continue

            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, bytes):
                import base64
                data[key] = base64.b64encode(value).decode("utf-8")
            else:
                data[key] = value

        model = instance or self

        # --- 1. Inject preloaded relationships into attribute space --- #
        preload_names = getattr(model, "_with_overrides", getattr(model, "__with__", []))
        for name in preload_names:
            cache_attr = f"_{name}_cache"
            if hasattr(self, cache_attr):
                cached = getattr(self, cache_attr)

                # Temporarily bind relationship to attribute (so accessors can work)
                setattr(self, name, cached)

                # Also serialize it for the output
                if isinstance(cached, ActiveRecord):
                    data[name] = cached.to_dict()
                elif isinstance(cached, list):
                    data[name] = [c.to_dict() if isinstance(c, ActiveRecord) else c for c in cached]
                else:
                    data[name] = cached or None

        # --- 2. Append computed attributes --- #
        for field in model.get_appends():
            accessor_name = f"get_{field}_attribute"
            if hasattr(model, accessor_name) and callable(getattr(model, accessor_name)):
                data[field] = getattr(model, accessor_name)()

        return DataKlass(data)

    # --------------------------------------------------------------------------
    # Hydration
    # --------------------------------------------------------------------------

    def _should_fire_event_during_hydration(self, event: str) -> bool:
        if event != "retrieved":
            return True

        cls = self.__class__
        has_retrieved_override = getattr(cls, "retrieved", None) is not getattr(Events, "retrieved", None)
        listeners = cls.__event_listeners__.get(cls, {})
        has_listeners = bool(listeners.get("retrieved") or listeners.get("__all__"))
        return has_retrieved_override or has_listeners

    def _hydrate_results(self: T, rows: list[dict], event: str = "retrieved") -> list[T]:
        if not rows:
            return []

        should_fire_event = self._should_fire_event_during_hydration(event)
        has_with_overrides = hasattr(self, "_with_overrides")
        has_appends = hasattr(self, "__appends__")

        # Fast path: plain model construction only.
        if not should_fire_event and not has_with_overrides and not has_appends:
            return [self.__class__(**row) for row in rows]

        results = []
        for row in rows:
            instance = self.__class__(**row)
            if has_with_overrides:
                instance._with_overrides = getattr(self, "_with_overrides")
            if has_appends:
                instance.__appends__ = getattr(self, "__appends__")
            if should_fire_event:
                self.fire_event(event, instance)
            results.append(instance)
        return results

    @staticmethod
    def _freeze_cache_value(value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(sorted((k, ActiveRecord._freeze_cache_value(v)) for k, v in value.items()))
        if isinstance(value, (list, tuple, set)):
            return tuple(ActiveRecord._freeze_cache_value(v) for v in value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    def _build_find_cache_key(self, query_obj: "ActiveRecord") -> tuple | None:
        if getattr(self, "__disable_request_find_cache__", False):
            return None
        try:
            sql, params = query_obj.get()
        except Exception:
            return None
        frozen_params = tuple(self._freeze_cache_value(p) for p in (params or ()))
        return (self.__class__, sql, frozen_params)

    def _get_request_find_cache(self) -> dict:
        try:
            from flask import g, has_request_context

            if has_request_context():
                cache = getattr(g, "_active_record_find_cache", None)
                if cache is None:
                    cache = {}
                    g._active_record_find_cache = cache
                return cache
        except Exception:
            pass

        cache = getattr(self, "_local_find_cache", None)
        if cache is None:
            cache = {}
            self._local_find_cache = cache
        return cache

    def _clear_request_find_cache(self):
        try:
            from flask import g, has_request_context

            if has_request_context() and hasattr(g, "_active_record_find_cache"):
                g._active_record_find_cache.clear()
        except Exception:
            pass

        if hasattr(self, "_local_find_cache"):
            self._local_find_cache.clear()

    # --------------------------------------------------------------------------
    # Retrieval - Bulk
    # --------------------------------------------------------------------------

    def all(self: T) -> ModelCollection[T]:
        self._apply_scopes_once_for_read()._apply_explicit_select_if_safe()
        rows = self.db.query(self)
        collection = ModelCollection(self._hydrate_results(rows))

        # ✅ preload relationships for .all() as well
        if getattr(self, "__with__", []) or getattr(self, "_with_overrides", None):
            BulkPreloader(collection, instance=self).run()

        return collection

    # --------------------------------------------------------------------------
    # Retrieval - Finders
    # --------------------------------------------------------------------------

    def find(self: T, id_: Any) -> Optional[T]:
        """
        Find a single record by its primary key.
        """
        if self.__driver__ == "mysql":
            q = self.where(self.__primary_key__, "=", id_)
        elif self.__driver__ == "mssql":
            q = (
                self.where(self.get_primary_key_column(), "=", id_)
                .order_by(self.get_primary_key_column(), "asc")
            )

        q._apply_scopes_once_for_read()._apply_explicit_select_if_safe()

        cache_key = self._build_find_cache_key(q)
        rows = None
        if cache_key is not None:
            rows = self._get_request_find_cache().get(cache_key)
        if rows is None:
            rows = self.db.query(q)
            if cache_key is not None:
                self._get_request_find_cache()[cache_key] = list(rows)
        else:
            rows = list(rows)
        if not rows:
            return None

        collection = ModelCollection(self._hydrate_results(rows))

        # ✅ preload relationships, but keep models
        if getattr(self, "__with__", []) or getattr(self, "_with_overrides", None):
            BulkPreloader(collection, instance=self).run()

        self._find_called()
        record = collection[0]
        setattr(record, "conditions", self.conditions)
        setattr(record, "parameters", self.parameters)
        return record

    def find_many(self: T, ids: list[Any] | tuple[Any, ...]) -> ModelCollection[T]:
        """
        Find many records by primary key while preserving input order.
        Missing IDs are skipped.
        """
        from framework1.database.active_record.utils.ModelCollection import ModelCollection

        if ids is None:
            return ModelCollection([])
        if not isinstance(ids, (list, tuple)):
            raise TypeError("ids must be a list or tuple")
        if not ids:
            return ModelCollection([])

        pk_col = self.get_primary_key_column()
        pk_leaf = pk_col.split(".")[-1] if "." in str(pk_col) else str(pk_col)

        # Query unique ids only (fewer bind params), but keep original order for output.
        unique_ids = []
        seen = set()
        for value in ids:
            marker = str(value)
            if marker in seen:
                continue
            seen.add(marker)
            unique_ids.append(value)

        q = self.where_in(pk_col, unique_ids)
        q._apply_scopes_once_for_read()._apply_explicit_select_if_safe()
        rows = self.db.query(q)
        if not rows:
            return ModelCollection([])

        collection = ModelCollection(self._hydrate_results(rows))

        if getattr(self, "__with__", []) or getattr(self, "_with_overrides", None):
            BulkPreloader(collection, instance=self).run()

        # Build lookup that tolerates type drift (e.g., input "10" vs DB int 10).
        by_pk = {}
        for record in collection:
            value = getattr(record, pk_leaf, None)
            if value is None and hasattr(record, "__data__"):
                value = record.__data__.get(pk_leaf)
            if value is None:
                continue
            by_pk.setdefault(value, record)
            by_pk.setdefault(str(value), record)

        ordered = []
        for requested in ids:
            record = by_pk.get(requested)
            if record is None:
                record = by_pk.get(str(requested))
            if record is not None:
                ordered.append(record)

        return ModelCollection(ordered)

    def find_or_fail(self, id: int, throw=None) -> T:
        class RecordNotFound:
            pass

        if not throw:
            throw = RecordNotFound

        record = self.find(id)
        if not record:
            raise throw(f"Record with ID {id} not found.")
        return record

    def find_or_404(self, id: int) -> T:
        class HttpNotFoundError(Exception):
            pass

        return self.find_or_fail(id, throw=HttpNotFoundError)



    def _find_called(self):
        """
        Internal method to track if find() was called.
        """
        self.__find_called__ = True
        return self.__find_called__

    def find_by(self: T, key, value) -> Optional[T]:
        """
        Find a single record by a specific column value.
        """
        q = self.new_query().where(key, "=", value).limit(1)
        q._apply_scopes_once_for_read()._apply_explicit_select_if_safe()
        rows = self.db.query(q)
        if not rows:
            return None

        self._find_called()
        instance = self.new_with_builder(q, **rows[0])
        self.fire_event("retrieved", instance)
        return instance

    def find_or_create_by(self, where: dict[str, Any], creates: dict[str, Any]) -> T:
        """
        Find a record or create it if not found.
        """
        found = self.where(where).first()
        if found:
            self.fire_event("retrieved", found)
            return found
        return self.create(**creates)

    def find_or_initialize_by(self, where: dict[str, Any], creates: dict[str, Any]) -> T:
        """
        Find a record or initialize it (unsaved) if not found.
        """
        found = self.where(where).first()
        return found if found else self.new(**creates)

    # --------------------------------------------------------------------------
    # Retrieval - Helpers
    # --------------------------------------------------------------------------

    def take(self, n: int = 1) -> Optional[T]:
        """
        Retrieve n records without any specific order.
        """
        if self.__driver__ in ("mysql", "mssql"):
            self.limit(n)
            if self.__driver__ == "mssql":
                self.order_by(self.get_primary_key_column())

        self._apply_scopes_once_for_read()._apply_explicit_select_if_safe()
        rows = self.db.query(*self.get())
        if not rows:
            return None
        results = self._hydrate_results(rows, event="retrieved")
        return results[0] if n == 1 else results

    def take_strict(self, n: int = 1) -> T:
        """
        Like take(), but raises if no records found.
        """
        result = self.take(n)
        if not result:
            raise RecordNotFound
        return result

    @override
    def where(self: T, *args: Any, **kwargs: Any) -> T:
        """
        Add WHERE conditions to the query.
        """
        return super().where(*args, **kwargs)

    def first(self: T, n: int = 1) -> T | List[T] | None:
        """
        Get the first n records ordered by primary key, with relationship preloading like `find`.
        """
        self.order_by(self.__primary_key__, "asc").limit(n)
        self._apply_scopes_once_for_read()._apply_explicit_select_if_safe()
        rows = self.db.query(*self.get())
        if not rows:
            return None

        # Hydrate into models
        collection = ModelCollection(self._hydrate_results(rows))

        # ✅ preload relationships (consistent with `find`)
        if getattr(self, "__with__", []) or getattr(self, "_with_overrides", None):
            BulkPreloader(collection, instance=self).run()

        results = []
        pagination_state = {
            "rows_fetch": getattr(self, "rows_fetch", None),
            "limit_count": getattr(self, "limit_count", None),
            "offset_count": getattr(self, "offset_count", None),
        }
        for record in collection:
            setattr(record, "conditions", self.conditions)
            setattr(record, "parameters", self.parameters)
            # Preserve pagination metadata so update/delete can strip stale params
            setattr(record, "rows_fetch", pagination_state["rows_fetch"])
            setattr(record, "limit_count", pagination_state["limit_count"])
            setattr(record, "offset_count", pagination_state["offset_count"])
            results.append(record)

        return results[0] if n == 1 else results

    def first_strict(self: T, n: int = 1) -> T | List[T]:
        """
        Like first(), but raises if no records found.
        """
        result = self.first(n)
        if not result:
            raise RecordNotFound
        return result

    @dualmethod
    def last(self: T, n: int = 1) -> T | List[T] | None:
        """
        Get the last n records ordered by primary key.
        """
        if isinstance(self, type):
            return self.order_by(self.get_primary_key_column(), "DESC").limit(n)
        else:
            self.order_by(self.get_primary_key_column(), "DESC").limit(n)
        self._apply_scopes_once_for_read()._apply_explicit_select_if_safe()
        rows = self.db.query(*self.get())
        if not rows:
            return None
        results = self._hydrate_results(rows, event="retrieved")

        return results[0] if n == 1 else results

    def last_strict(self: T, n: int = 1) -> T:
        """
        Like last(), but raises if no records found.
        """
        result = self.last(n)
        if not result:
            raise RecordNotFound
        return result

    # --------------------------------------------------------------------------
    # Aggregates & Pagination
    # --------------------------------------------------------------------------
    def count(self, column: str = "*", alias: str = "aggregate") -> ModelCollection:
        self.as_count(column, alias)
        rows = self.db.query(self)
        return ModelCollection(rows).first()[alias]

    @staticmethod
    def _extract_count_value(row: Any) -> int:
        if hasattr(row, "get"):
            for key in ("count", "COUNT", "aggregate", "AGGREGATE"):
                if key in row:
                    return int(row[key])
            # case-insensitive fallback
            lowered = {str(k).lower(): v for k, v in row.items()}
            if "count" in lowered:
                return int(lowered["count"])
        if isinstance(row, dict):
            for key in ("count", "COUNT", "aggregate", "AGGREGATE"):
                if key in row:
                    return int(row[key])
        raise KeyError("Unable to resolve count column from count query result.")

    def _build_paginate_count_query(self):
        """
        Build an exact, minimal count query for pagination.
        Keeps filtering semantics while stripping expensive read-shape clauses.
        """
        count_query = self.clone_without_columns_or_ordering().without_scopes()
        count_query.columns = [Raw("COUNT(*) as count")]
        count_query.order_by_clause = None
        count_query.order_by_clauses = []
        count_query.limit_count = None
        count_query.offset_count = None
        count_query.rows_fetch = None

        # The count query must not re-apply scopes when serialized.
        if hasattr(count_query, "__scopes_enabled__"):
            count_query.__scopes_enabled__ = False

        # Keep only bindings referenced by the resulting count SQL.
        count_sql = count_query.to_sql(include_select=True)
        placeholder_count = count_sql_placeholders(count_sql)
        count_query.parameters = list(count_query.parameters[:placeholder_count])
        return count_query

    def paginate(self: T, page: int = 1, per_page: int = 10, count_total: bool = True) -> PaginationResult:
        from framework1.database.active_record.utils.ModelCollection import ModelCollection

        """
        Paginate results with database-level pagination.
        """
        # Apply scopes once up-front so placeholder order remains stable.
        # If scopes are applied later during to_sql(), they append WHERE params
        # after LIMIT/OFFSET params and can break parameter ordering.
        self._apply_scopes_once_for_read()
        self._apply_explicit_select_if_safe()

        # Reset pagination-related attributes
        self.limit_count = None
        self.offset_count = None
        self.rows_fetch = None
        self.parameters = self.get_parameters()

        total = None
        if count_total:
            count_query = self._build_paginate_count_query()
            count_rows = self.db.query(count_query)
            if count_rows:
                total = self._extract_count_value(count_rows[0])
            else:
                total = 0

        page_size = per_page if count_total else per_page + 1

        # Apply pagination on the current scoped query.
        super().paginate(page, page_size)

        # Fetch paginated rows
        rows = self.db.query(*self.get())

        has_next = False
        if not count_total and len(rows) > per_page:
            has_next = True
            rows = rows[:per_page]

        # Hydrate rows and fire events
        items = ModelCollection(self._hydrate_results(rows))
        BulkPreloader(items).run()

        if not count_total:
            return SimplePaginationResult(
                items=items,
                per_page=per_page,
                current_page=page,
                has_next=has_next,
            )

        return PaginationResult(
            items=items,
            total=total,
            per_page=per_page,
            current_page=page
        )

    # --------------------------------------------------------------------------
    # Persistence - Create & Save
    # --------------------------------------------------------------------------

    @classmethod
    def create(cls: Type[T], **kwargs: Any) -> T:
        """
        Create a new model instance with the given attributes and save it to the database.
        """
        instance = cls(**kwargs)
        instance._created_by_create = True  # Prevent double event firing

        # Fire lifecycle events before save
        instance.fire_event("creating", instance)
        instance.fire_event("saving", instance)

        instance.save(is_from_create=True)

        # Fire lifecycle events after save
        instance.fire_event("created", instance)
        instance.fire_event("saved", instance)
        instance.__original__ = instance.__data__.copy()

        return instance

    def save(self, has_triggers=False, is_from_create=False) -> Any:
        """
        Insert or update the current model instance in the database.
        Handles lifecycle events before/after persistence.
        """
        now = datetime.utcnow().isoformat()
        pk = self.get_primary_key_column()
        record_pk = self.__data__.get(pk)
        self.original = self.__data__

        fields = self.get_fields()
        # Track differences
        changed_fields = {}
        for k, v in self.__data__.items():
            original_val = self.__original__.get(k) if hasattr(self, "__original__") else None
            if v != original_val:
                changed_fields[k] = v

        # Drop None and unknown fields
        data = {k: v for k, v in self.__data__.items() if k in fields and v is not None}

        # Ensure JSON fields are serialized for the DB driver (e.g., pyodbc)
        changed_fields = self._serialize_fields(changed_fields)
        data = self._serialize_fields(data)

        # ---------------------
        # UPDATE PATH
        # ---------------------
        if not is_from_create and record_pk:
            # No actual changes
            if not changed_fields:
                return record_pk

            # Fire before update
            self.fire_event("updating", self)
            self.fire_event("saving", self)

            # Set timestamp

            if not getattr(self, "__timestamps_disabled__", False):
                updated_field = self.__timestamps_override__.get("updated_at")
                if updated_field and hasattr(self, updated_field):
                    changed_fields[updated_field] = now

            # Remove primary key from update values
            update_values = {k: v for k, v in changed_fields.items() if k != pk}

            if not update_values:
                return record_pk

            # Build SQL
            builder = QueryBuilder().table(self.__class__.__table__) \
                .where(self.get_primary_key_column(), "=", record_pk)

            sql, params = builder.update(update_values)

            logger.debug(f"[UPDATE SQL] {sql} params={params}")

            # Ensure parameters are in proper order
            params = list(update_values.values()) + [record_pk]

            # Execute the update
            self.db.query(sql, params)
            self.db.connection.commit()
            self._clear_request_find_cache()

            # Fire after update
            self.fire_event("updated", self)
            self.fire_event("saved", self)
            self.__original__ = self.__data__.copy()

            return data.get(pk, record_pk)  # return primary key field value

        else:
            # Insert path
            if not getattr(self, "__timestamps_disabled__", False):
                if hasattr(self, self.__timestamps_override__.get("created_at")):
                    data.setdefault(self.__timestamps_override__.get("created_at"), now)
                if hasattr(self, self.__timestamps_override__.get("updated_at")):
                    data.setdefault(self.__timestamps_override__.get("updated_at"), now)

            # Fire events only if not created via .create()
            if not getattr(self, "_created_by_create", False):
                self.fire_event("creating", self)
                self.fire_event("saving", self)

            q = self.insert(data, has_triggers=has_triggers)
            with self.db.connect() as cursor:
                logger.debug(f"[INSERT SQL] {q}")
                cursor.execute(*q)
                if self.__driver__ == "mysql":
                    last_id = cursor.lastrowid
                elif self.__driver__ == "mssql":
                    last_id = None
                    if not has_triggers:
                        row = cursor.fetchone()
                        if row:
                            # try attribute (pyodbc.Row) then index 0
                            if hasattr(row, self.get_primary_key_column()):
                                last_id = getattr(row, self.get_primary_key_column())
                            elif len(row):
                                last_id = row[0]
                    if not last_id:
                        cursor.execute("SELECT SCOPE_IDENTITY() AS last_id")
                        last_id = cursor.fetchone().last_id

                self.db.connection.commit()
                self._clear_request_find_cache()

                if last_id:
                    data[pk] = last_id
                    # keep instance in sync with generated PK
                    self.__data__[pk] = last_id
                else:
                    logger.warning("Failed to get last insert ID")
                    data[pk] = None

            if not getattr(self, "_created_by_create", False):
                self.fire_event("created", self)
                self.fire_event("saved", self)
                self.__original__ = self.__data__.copy()

            return data[pk]

    # --------------------------------------------------------------------------
    # Persistence - Bulk Insert
    # --------------------------------------------------------------------------

    @classmethod
    def create_bulk(cls: Type[T], records: List[dict], ignore=False) -> List[T]:
        """
        Bulk create model instances in a cross-compatible way.
        - MySQL: uses single execute with multi-row VALUES.
        - MSSQL: uses executemany with a single-row VALUES template.
        """
        if not records:
            return []

        now = datetime.utcnow().isoformat()
        instances = []
        db_instance = cls().db
        pk = cls().get_primary_key_column()

        # Create instances + lifecycle events
        for record in records:
            record = normalize_values(record)
            if "created_at" not in record:
                record.setdefault("created_at", now)
                record.setdefault("updated_at", now)
            instance = cls(**record)
            instance.fire_event("creating", instance)
            instance.fire_event("saving", instance)
            instances.append(instance)

        # Generate SQL + params
        serialized_rows = [inst._serialize_fields(inst.__data__) for inst in instances]
        sql, params, use_executemany = cls().insert_many(serialized_rows, ignore=ignore)

        driver = getattr(cls, "__driver__", "mysql")

        try:
            connection = db_instance.connection
            with db_instance.connect() as cursor:
                if use_executemany:
                    cursor.executemany(sql, params)
                else:
                    cursor.execute(sql, params)

                if driver == "mysql":
                    last_id = cursor.lastrowid
                    db_instance.connection.commit()

                    if last_id:
                        for i, instance in enumerate(instances):
                            instance.__data__[pk] = last_id + i
                            instance.__original__ = instance.__data__.copy()
                            instance.fire_event("created", instance)
                            instance.fire_event("saved", instance)
                else:
                    # MSSQL: commit without trying to guess IDs
                    db_instance.connection.commit()
                    for instance in instances:
                        instance.__original__ = instance.__data__.copy()
                        instance.fire_event("created", instance)
                        instance.fire_event("saved", instance)

        except Exception as e:
            if connection:
                connection.rollback()
            raise e

        cls()._clear_request_find_cache()
        return instances

    # --------------------------------------------------------------------------
    # Persistence - Update
    # --------------------------------------------------------------------------

    def _execute_write(self, sql: str, params: tuple | list):
        """
        Execute a write (insert/update/delete) with logging, commit, and cleanup.
        Keeps a live connection through commit to avoid MySQL 'server has gone away'
        when connections are closed before committing.
        """
        start_time = time.perf_counter()
        # Normalize param placeholders for MSSQL/pyodbc which expects '?' markers
        driver = getattr(self, "__driver__", None)
        if driver == "mssql":
            sql = sql.replace("%s", "?")

        cursor = self.db.connect()
        cursor.execute(sql, params)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        # Log if available on the db adapter
        log_fn = getattr(self.db, "_log_query", None)
        if callable(log_fn):
            log_fn(sql, params, elapsed_ms)
        self.db.connection.commit()
        rowcount = getattr(cursor, "rowcount", 0)
        cleanup = getattr(self.db, "_cleanup", None)
        if callable(cleanup):
            cleanup()
        self._clear_request_find_cache()
        return rowcount

    @override
    def update(self, values: dict[str, Any] = None, **kwargs) -> Any:
        """
        Update model attributes in the database.

        Supports three modes:
        - Single instance update (fires lifecycle events).
        - Bulk update with events.
        - Fast raw bulk update without events.
        """
        # support both positional dict and kwargs
        if values is None:
            values = {}
        values = {**values, **kwargs}

        self.remove_limit()

        primary_key = self.get_primary_key_column()
        values = {k: v for k, v in values.items() if k != primary_key}

        # Check if this is a model instance (e.g. from .find())
        is_instance = hasattr(self, "__data__")

        if is_instance:
            # Instance update path
            for key, value in values.items():
                self.__data__[key] = value

            self.fire_event("updating", self)
            self.fire_event("saving", self)

            sql, params = super().update(values)

            self._execute_write(sql, params)

            self.fire_event("updated", self)
            self.fire_event("saved", self)

            primary_key = getattr(self, self.get_primary_key_column())
            return self.clone_without_columns_or_ordering().where(self.get_primary_key_column(), primary_key).first()

        # Bulk update with events
        elif self._with_events:
            rows = self.db.query(self)
            pk = self.get_primary_key_column()

            affected = 0
            for row in rows:
                instance = self.__class__(**row)

                for key, value in values.items():
                    instance.__data__[key] = value

                instance.fire_event("updating", instance)
                instance.fire_event("saving", instance)

                q = self.new_query().where(pk, "=", row[pk]).update(values)
                sql, params = q
                affected += self._execute_write(sql, params)

                instance.fire_event("updated", instance)
                instance.fire_event("saved", instance)

            self.__original__ = self.__data__.copy()
            return affected

        # Fast bulk update with no events
        else:
            sql, params = super().update(values)
            self._execute_write(sql, params)
            self.__original__ = self.__data__.copy()
            return True

    # --------------------------------------------------------------------------
    # Persistence - Delete
    # --------------------------------------------------------------------------

    @override
    def delete(self, id: int | None = None) -> T | int:
        """
        Delete a model instance or matching records.

        Supports:
        - Direct instance deletes (fires events).
        - Query-based deletes with optional lifecycle events.
        """
        self.remove_limit()
        pk = self.get_primary_key_column()

        is_find_based = False

        if not self.conditions:
            # Delete by primary key
            self.__find_called__ = False
            super().where(pk, '=', id)
        else:
            self.__find_called__ = True
            is_find_based = hasattr(self, "__data__")

        # Fire "deleting" events before query delete if using .with_events()
        if self._with_events and not is_find_based:
            rows = self.db.query(self)
            for row in rows:
                inst = self.__class__(**row)
                inst.fire_event("deleting", inst)

        sql, params = super().delete()
        affected_rows = self._execute_write(sql, params)

        # Fire "deleted" events
        if self._with_events and not is_find_based:
            for row in rows:
                inst = self.__class__(**row)
                inst.fire_event("deleted", inst)

        elif affected_rows == 1 and is_find_based:
            self.fire_event("deleted", self)
            return self.__class__(**self.__data__)

        return affected_rows

    # --------------------------------------------------------------------------
    # DATA TRANSFER OBJECTS
    # --------------------------------------------------------------------------
    def to_dto(self, target: str):
        """
        Find and call a decorated @dto function by suffix.
        Example: model.to_dto("primacy")
        """
        for attr_name in dir(self):
            fn = getattr(self, attr_name, None)
            if callable(fn) and getattr(fn, "__is_dto_mapper__", False):
                if attr_name.endswith(target):
                    return fn()  # 👈 decorator now handles mapping + row
        raise ValueError(f"No DTO mapper found for target '{target}' in {self.__class__.__name__}")

    def run_batch_queries(self, filter_dict: dict[str, QueryBuilder] | dict[str, str]):
        """
        Perform batch queries on a model class using the provided filter dictionary.
        Each key in the filter_dict corresponds to a query to be executed.
        """
        results = {}
        results = self.db.pquery(filter_dict)
        merged_results = {}
        for result in results:
            merged_results.update(
                DataKlass({
                    list(result.keys())[0]: DataKlass(result.get(list(result.keys())[0])[0])
                })
            )
        return DataKlass(merged_results)
