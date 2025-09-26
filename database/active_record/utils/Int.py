

from framework1.database.QueryBuilder import QueryBuilder
from typing import TypeVar

T = TypeVar("T", bound="ActiveRecord")


class ActiveRecordUtilitiesInt():
    from framework1.database.active_record.Logging import logger
    def is_loaded(self) -> bool:
        return bool(self.__data__)

    def get_table(self) -> str:
        return getattr(self, "__table__", "")

    def get_primary_key_column(self) -> str:
        return getattr(self, "__primary_key__", "id")

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
        # using the provided scopes, pluck them from the current assume that scopes are already in self.__scopes__. scopes are a list of dictionaries. the keys are the scope names and the values are the methods.
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
                # If the base class is a scope, add its apply method to the scopes list
                if hasattr(base, "apply"):
                    scope = {base.__qualname__: base.apply}
                    self.__scopes__.append(scope)
        return self.__scopes__

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
    
    
