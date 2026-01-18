from _collections_abc import Iterable
from typing import TypeVar, List, Any, Callable
import pprint
from framework1.database.BulkPreloader import BulkPreloader
T = TypeVar('T')



class ModelCollection(list, Iterable):
    def __init__(self, items: List[T] | Callable[[], list[Any]] = []):
        super().__init__(items)

    def to_list_dict(self, instance=None) -> List[dict[str, Any]]:
        BulkPreloader(self, instance=instance).run()
        return [m.to_dict(instance=instance) for m in self]

    def to_dtos(self, target: str) -> List[Any]:
        """
        Convert all models to DTOs for the given target.
        Example:
            clients.to_dtos("primacy")
        """
        return [item.to_dto(target) for item in self]

    def pluck(self, column: str) -> List[Any]:
        """Get a list of values from a specific column"""
        return [getattr(model, column) for model in self]

    def where(self, callback) -> 'ModelCollection':
        """Filter the collection using a callback"""
        return ModelCollection([item for item in self if callback(item)])

    def first(self):
        """Get first item from collection"""
        return self[0] if len(self) > 0 else None

    def take(self, n=1):
        return self[:n]

    def last(self):
        """Get last item from collection"""
        return self[-1] if len(self) > 0 else None

    def count(self):
        """Get count of items in collection"""
        return len(self)

    def order_by(self, *fields) -> 'ModelCollection':
        """
        Sort the collection by one or more fields.

        Usage:
            collection.order_by("name")
            collection.order_by("-created_at")
            collection.order_by(("age", "desc"))
            collection.order_by("age", "-balance", ("created_at", "asc"))
        """

        sort_instructions = []

        for field in fields:
            # Case: "name" or "-name"
            if isinstance(field, str):
                if field.startswith("-"):
                    sort_instructions.append((field[1:], True))
                else:
                    sort_instructions.append((field, False))

            # Case: ("name", "asc") or ("name", "desc")
            elif isinstance(field, tuple) and len(field) == 2:
                fname, direction = field
                descending = str(direction).lower() in ("desc", "descending", "-")
                sort_instructions.append((fname, descending))

            else:
                raise ValueError(f"Invalid order_by argument: {field}")

        # Python sorts are stable → apply last instruction first
        sorted_items = list(self)
        for fname, desc in reversed(sort_instructions):
            sorted_items.sort(key=lambda item: getattr(item, fname), reverse=desc)

        return ModelCollection(sorted_items)