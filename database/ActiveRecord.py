import pprint

import inflect
import re
from copy import deepcopy
from datetime import datetime
from framework1.core_services.Database import Database
from framework1.database.Events import Events
from framework1.database.active_record.utils.ModelCollection import ModelCollection
from framework1.database.fields.Fields import Field
from framework1.utilities.DataKlass import DataKlass
from functools import wraps
from slugify import slugify
from typing import Any, TypeVar, Type, Optional, Self, List, NoReturn, override, Callable
from dotenv import load_dotenv
import inspect
from framework1.ddd.ValueObject import ValueObject
from operator import itemgetter

load_dotenv()
p = inflect.engine()

from framework1.database.QueryBuilder import QueryBuilder

from datetime import datetime, date

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
            dto_cls = fn.__annotations__.get("return")   # get DTO class
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

def get_relationship_type(fn) -> str:
    if (getattr(fn, "__has_one__", False)
            or getattr(fn, "__belongs_to__", False)
            or getattr(fn, "__has_one_through__", False)):
        return "one"
    else:
        return "many"


def remove_first_condition(query_obj: QueryBuilder, clone: bool = True) -> QueryBuilder:
    """
    Safely remove the first WHERE condition and its bound parameter.

    Args:
        query_obj: The query builder or ActiveRecord instance.
        clone: If True, returns a cloned copy; if False, mutates in place.

    Returns:
        QueryBuilder with first condition + parameter removed.
    """
    target = deepcopy(query_obj) if clone else query_obj

    if getattr(target, "conditions", None):
        target.conditions = target.conditions[1:]

    if getattr(target, "parameters", None):
        target.parameters = target.parameters[1:]

    return target


class Relationship:
    def add_constraints(self, models: List["ActiveRecord"]):
        ...

    def match(self, results):
        ...


def bulk_preload_withs(models: "ModelCollection", instance: Optional[Type[Self]] = None):
    from framework1.database.active_record.utils.ModelCollection import ModelCollection
    """
    Bulk preloads __with__ relationships for a collection of models.
    Supports nested relationships like __with__ = ["client.alerts"].
    Requires relationship functions to define both foreign_key and owner_key.
    """
    if not models:
        return

    primary_model = models[0]

    # 👇 choose source of withs
    if instance is None:
        if getattr(primary_model, "_with_overrides", None) is not None:
            withs = primary_model._with_overrides
        else:
            withs = getattr(primary_model, "__with__", [])
    else:
        if getattr(instance, "_with_overrides", None) is not None:
            withs = instance._with_overrides
        else:
            withs = getattr(instance, "__with__", [])
    if not withs:
        return


    # Build tree so we know nested structure
    with_tree = parse_withs(withs)

    queries_for_pquery = []
    params_for_pquery = []
    join_meta = []

    # --- Build queries for top-level only ---
    for relationship, nested in with_tree.items():
        relationship_query = getattr(primary_model, relationship)()
        database = getattr(relationship_query, "db")


        rel_cls = relationship_query.__class__

        # Detect relationship type
        rel_type = get_relationship_type(relationship_query)

        fk_field = getattr(relationship_query, "__foreign_key__", None)
        owner_field = getattr(relationship_query, "__owner_key__", None)

        if not getattr(relationship_query, '__match_fn__', None) and not getattr(relationship_query, '__constraints__', None):
            if not fk_field or not owner_field:
                raise Exception(
                    f"Relationship '{relationship}' did not define foreign_key/owner_key properly"
                )

        if rel_type == "many":
            # collect parent.owner_key values
            if getattr(relationship_query, "__constraints__", None):
                bulk_query = getattr(relationship_query, "__constraints__")
            else:
                ids = [m.__data__.get(owner_field) for m in models if m.__data__.get(owner_field)]
                bulk_query = (
                    remove_first_condition(relationship_query).where_in(fk_field, ids)
                )
        else:
            # belongs_to / has_one: collect parent.foreign_key values
            parent_fk_values = [
                getattr(m, fk_field)
                for m in models
                if getattr(m, fk_field, None)
            ]
            #raise Exception(relationship_query.__dict__)
            bulk_query = (
                remove_first_condition(relationship_query)
                .where_in(owner_field, parent_fk_values)
            )



        queries_for_pquery.append({
            relationship: bulk_query.to_sql(),
            "db": database.__class__.__name__,
            "params": bulk_query.parameters,
            'db_instance': database
        })
        #params_for_pquery.extend()
        join_meta.append({
            "rel": relationship,
            "fk_field": fk_field,
            "rel_type": rel_type,
            "rel_cls": rel_cls,
            "nested_withs": nested,
            "foreign_key": fk_field,
            "owner_key": owner_field,
            "match_fn": getattr(relationship_query, '__match_fn__', None),
            "constraints": getattr(relationship_query, '__constraints__', None)
        })

    if not queries_for_pquery:
        return

    pquery_results = []
    databases = ModelCollection(list(set([key['db'] for key in queries_for_pquery])))
    queries_for_pquery = ModelCollection(queries_for_pquery)
    for db in databases:
        db_instance = queries_for_pquery.where(lambda q: q['db'] == db).first()['db_instance']
        queries_for_this_db = []
        params_for_this_db = []
        for q in queries_for_pquery.where(lambda q: q['db'] == db):
            q = deepcopy(q)
            params = q['params']
            q.pop('db')
            q.pop('db_instance')
            q.pop('params')
            queries_for_this_db.append(q)
            params_for_this_db.extend(params)

        results_from_this_db = db_instance.pquery(queries_for_this_db, *params_for_this_db)
        pquery_results.append(results_from_this_db)



    pquery_results = [item for sublist in pquery_results for item in sublist]


    # Map results
    rel_results_by_name = {}
    for res in pquery_results:
        for key, rows in res.items():
            rel_results_by_name[key] = [dict(r) for r in rows]


    # Assign hydrated results
    for model in models:
        for meta in join_meta:
            rel_name = meta["rel"]
            fk_field = meta["fk_field"]
            rel_type = meta["rel_type"]
            rel_cls = meta["rel_cls"]
            nested_withs = meta["nested_withs"]
            owner_field = meta["owner_key"]
            match_fn = meta["match_fn"]
            constraints = meta["constraints"]

            if rel_name not in rel_results_by_name or not rel_cls:
                setattr(model, f"_{rel_name}_cache", None if rel_type == "one" else [])
                continue

            raw_rows = rel_results_by_name[rel_name]
            if not match_fn and not constraints:
                hydrated = rel_cls()._hydrate_results(raw_rows) if raw_rows else []
            else:
                hydrated = raw_rows

            if rel_type == "many":
                if not match_fn and not constraints:
                    pk_val = model.__data__.get(owner_field)
                    related = [r for r in hydrated if r.__data__.get(fk_field) == pk_val]
                    setattr(model, f"_{rel_name}_cache", related)
                else:
                    related = getattr(relationship_query, '__match_fn__', None)(hydrated)
                    setattr(model, f"_{rel_name}_cache", related)

                if nested_withs and related:
                    for r in related:
                        r.__with__ = [
                            f"{k}" if not v else f"{k}.{'.'.join(v.keys())}"
                            for k, v in nested_withs.items()
                        ]
                    bulk_preload_withs(ModelCollection(related))

            else:  # one
                parent_fk_val = getattr(model, fk_field, None)
                related = next(
                    (r for r in hydrated if getattr(r, owner_field) == parent_fk_val),
                    None
                )
                setattr(model, f"_{rel_name}_cache", related)

                if nested_withs and related:
                    related.__with__ = [
                        f"{k}" if not v else f"{k}.{'.'.join(v.keys())}"
                        for k, v in nested_withs.items()
                    ]
                    bulk_preload_withs(ModelCollection([related]))


def mark_relationship(query, rel_type: str, owner_key: str = None, foreign_key: str = None) -> QueryBuilder:
    query.__is_relationship__ = True
    setattr(query, f"__{rel_type}__", True)
    query.__owner_key__ = owner_key
    query.__foreign_key__ = foreign_key

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


T = TypeVar("T", bound="ActiveRecord")


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

        self.fill(**kwargs)

    def get_appends(self):
        """
        Returns the list of appended fields.
        """
        return self.__appends__

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
        new_instance = self.__class__()
        new_instance.columns = self.columns[:]
        new_instance.conditions = self.conditions[:]
        new_instance.parameters = self.parameters[:]
        return new_instance

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

    def belongs_to(self, model, foreign_key: str = None, owner_key: str = None):
        related_model = model()
        related_table = model.__table__

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

    def has_many(self, model, foreign_key: str = None, local_key: str = None):
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
        return mark_relationship(query, "has_many", owner_key=local_key, foreign_key=foreign_key)

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

    def with_only(self, withs: list[str]) -> "Self":
        """
        Replace relationships entirely for this instance only.
        """
        self._with_overrides = expand_withs(withs)
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

    # --------------------------------------------------------------------------
    # Basic Model Information
    # --------------------------------------------------------------------------

    def is_loaded(self) -> bool:
        return bool(self.__data__)

    def get_table(self) -> str:
        return getattr(self, "__table__", "")

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
    def generate_schema(cls) -> str:
        fields = cls.get_fields()
        if not fields:
            raise ValueError(f"{cls.__name__} has no declared fields.")

        columns = []
        pk = None

        for name, field in fields.items():
            col_def = f"`{name}` {field.get_sql_type()}"

            if field.collation:
                col_def += f" COLLATE {field.collation}"
            if not field.nullable:
                col_def += " NOT NULL"
            if field.unique:
                col_def += " UNIQUE"
            if field.default is not None:
                if isinstance(field.default, str) and field.default.upper() in ("CURRENT_TIMESTAMP", "NOW()"):
                    col_def += f" DEFAULT {field.default}"
                elif isinstance(field.default, (int, float)):
                    col_def += f" DEFAULT {field.default}"
                else:
                    col_def += f" DEFAULT '{field.default}'"
            if field.comment:
                col_def += f" COMMENT '{field.comment}'"

            if field.primary_key:
                pk = name

            columns.append(col_def)

        if pk:
            columns.append(f"PRIMARY KEY (`{pk}`)")

        table_name = getattr(cls, "__table__", cls.__name__)
        return f"CREATE TABLE IF NOT EXISTS `{table_name}` (\n  " + ",\n  ".join(columns) + "\n);"

    @classmethod
    def create_table(cls) -> None:
        sql = cls.generate_schema()
        db = cls.__database__()
        db.query(sql)
        db.connection.commit()
        print(f"✔ Table `{cls.__table__}` created.")

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

        # Serialize stored DB fields
        for key, value in self.__data__.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, bytes):
                import base64
                data[key] = base64.b64encode(value).decode("utf-8")
            elif isinstance(value, ActiveRecord):
                data[key] = value.to_dict()
            elif isinstance(value, list) and all(isinstance(x, ActiveRecord) for x in value):
                data[key] = [x.to_dict() for x in value]
            else:
                data[key] = value

        model = instance or self

        # --- Handle appended/computed attributes ---
        for field in model.get_appends():
            accessor_name = f"get_{field}_attribute"
            if hasattr(model, accessor_name) and callable(getattr(model, accessor_name)):
                data[field] = getattr(model, accessor_name)()

        # Serialize preloaded relationships
        if hasattr(model, "_with_overrides") or hasattr(model, "__with__"):
            for name in getattr(model, "_with_overrides", getattr(model, "__with__")):
                cache_attr = f"_{name}_cache"
                if hasattr(self, cache_attr):
                    cached = getattr(self, cache_attr)
                    if isinstance(cached, ActiveRecord):
                        data[name] = cached.to_dict()
                    elif isinstance(cached, list):
                        if len(cached) != 0:
                            if isinstance(cached[0], ActiveRecord):
                                data[name] = [c.to_dict() for c in cached]
                            elif isinstance(cached[0], dict):
                                data[name] = cached
                            elif isinstance(cached[0], ModelCollection):
                                data[name] = cached
                        else:
                            data[name] = []

                    else:
                        # Unexpected preload type → fallback to None
                        data[name] = None
        return DataKlass(data)

    # --------------------------------------------------------------------------
    # Hydration
    # --------------------------------------------------------------------------

    def _hydrate_results(self: T, rows: list[dict], event: str = "retrieved") -> list[T]:
        cls = self.__class__
        fire_event = self.fire_event

        results = []
        for row in rows:
            instance = cls(**row)
            #fire_event(event, instance)
            results.append(instance)
        return results

    # --------------------------------------------------------------------------
    # Retrieval - Bulk
    # --------------------------------------------------------------------------

    def all(self: T) -> ModelCollection[T]:
        rows = self.db.query(self)
        collection = ModelCollection(self._hydrate_results(rows))

        # ✅ preload relationships for .all() as well
        if getattr(self, "__with__", []) or getattr(self, "_with_overrides", None):
            bulk_preload_withs(collection, instance=self)

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

        rows = self.db.query(q)
        if not rows:
            return None

        collection = ModelCollection(self._hydrate_results(rows))

        # ✅ preload relationships, but keep models
        if getattr(self, "__with__", []) or getattr(self, "_with_overrides", None):
            bulk_preload_withs(collection, instance=self)

        self._find_called()
        record = collection[0]
        setattr(record, "conditions", self.conditions)
        setattr(record, "parameters", self.parameters)
        return record

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

        rows = self.db.query(*self.get())
        if not rows:
            return None

        results = []
        for row in rows:
            instance = self.__class__(**row)
            self.fire_event("retrieved", instance)
            results.append(instance)
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
        Get the first n records ordered by primary key.
        """
        self.order_by(self.__primary_key__, "asc").limit(n)
        rows = self.db.query(*self.get())
        if not rows:
            return None

        results = []
        for row in rows:
            instance = self.__class__(**row)
            self.fire_event("retrieved", instance)
            results.append(instance)

        return results[0] if n == 1 else results

    def first_strict(self: T, n: int = 1) -> T | List[T]:
        """
        Like first(), but raises if no records found.
        """
        result = self.first(n)
        if not result:
            raise RecordNotFound
        return result

    def last(self: T, n: int = 1) -> T | List[T] | None:
        """
        Get the last n records ordered by primary key.
        """
        self.order_by(self.get_primary_key_column(), "DESC").limit(n)
        rows = self.db.query(*self.get())
        if not rows:
            return None

        results = []
        for row in rows:
            instance = self.__class__(**row)
            self.fire_event("retrieved", instance)
            results.append(instance)

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

    def count(self):
        self.select("COUNT(*) as count")
        return self.all()[0].to_dict().get("count")

    def paginate(self: T, page: int = 1, per_page: int = 10) -> PaginationResult:
        from framework1.database.active_record.utils.ModelCollection import ModelCollection
        from framework1.database.ActiveRecord import bulk_preload_withs

        """
        Paginate results with database-level pagination.
        """
        # Reset pagination-related attributes
        self.limit_count = None
        self.offset_count = None
        self.rows_fetch = None
        self.parameters = self.get_parameters()

        # Clone to get total count
        count_query = self.clone_without_columns_or_ordering().without_scopes()
        count_query.columns = [f"COUNT(*) as count"]
        count_query.order_by_clause = None

        try:
            total = self.db.query(count_query)[0]["count"]
        except KeyError:
            total = self.db.query(count_query)[0]["COUNT"]

        # Apply pagination
        super().paginate(page, per_page).without_scopes()

        # Fetch paginated rows
        rows = self.db.query(*self.get())

        # Hydrate rows and fire events
        items = ModelCollection(self._hydrate_results(rows))
        bulk_preload_withs(items)

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

        instance.save()

        # Fire lifecycle events after save
        instance.fire_event("created", instance)
        instance.fire_event("saved", instance)
        instance.__original__ = instance.__data__.copy()

        return instance

    def save(self) -> Any:
        """
        Insert or update the current model instance in the database.
        Handles lifecycle events before/after persistence.
        """
        now = datetime.utcnow().isoformat()
        pk = self.get_primary_key_column()
        data = self.__data__

        if pk in data:
            # Update path
            if data == self.__original__:
                return data[pk]

            # Fire before update
            self.fire_event("updating", self)
            self.fire_event("saving", self)

            data.setdefault("updated_at", now)
            q = self.where(pk, "=", data[pk]).update(data)
            result = self.db.query(*q)
            self.db.connection.commit()

            # Fire after update
            self.fire_event("updated", self)
            self.fire_event("saved", self)
            self.__original__ = self.__data__.copy()
            return data[pk]

        else:
            # Insert path
            if hasattr(self, "created_at"):
                data.setdefault("created_at", now)
            if hasattr(self, "updated_at"):
                data.setdefault("updated_at", now)

            # Fire events only if not created via .create()
            if not getattr(self, "_created_by_create", False):
                self.fire_event("creating", self)
                self.fire_event("saving", self)

            q = self.insert(data)
            with self.db.connect() as cursor:
                cursor.execute(*q)
                if self.__class__.__driver__ != "mssql":
                    last_id = cursor.lastrowid
                else:
                    cursor.execute("SELECT SCOPE_IDENTITY()")
                    last_id = cursor.fetchone()[0]
                self.db.connection.commit()

                if last_id:
                    data[pk] = last_id
                else:
                    print("Failed to get last insert ID")
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
        sql, params, use_executemany = cls().insert_many(
            [inst.__data__ for inst in instances], ignore=ignore
        )

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

        return instances

    # --------------------------------------------------------------------------
    # Persistence - Update
    # --------------------------------------------------------------------------

    @override
    def update(self, values: dict[str, Any]) -> Any:
        """
        Update model attributes in the database.

        Supports three modes:
        - Single instance update (fires lifecycle events).
        - Bulk update with events.
        - Fast raw bulk update without events.
        """
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
            if isinstance(params, list):
                params = [p for p in params if p != 1]

            self.db.query(sql, params)
            self.db.connection.commit()

            self.fire_event("updated", self)
            self.fire_event("saved", self)
            return True

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
                self.db.query(sql, params)
                affected += self.db.cursor.rowcount

                instance.fire_event("updated", instance)
                instance.fire_event("saved", instance)

            self.db.connection.commit()
            self.__original__ = self.__data__.copy()
            return affected

        # Fast bulk update with no events
        else:
            sql, params = super().update(values)
            if isinstance(params, list):
                params = [p for p in params if p != 1]

            self.db.query(sql, params)
            self.db.connection.commit()
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
        self.parameters = [p for p in self.parameters if p != 1]
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
        self.db.query(sql, params)
        affected_rows = self.db.cursor.rowcount
        self.db.connection.commit()

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