from typing import TypeVar, List, Any
import pprint

T = TypeVar('T')



class ModelCollection(list):
    def __init__(self, items: List[T]):
        super().__init__(items)

    def to_list_dict(self, instance=None) -> List[dict[str, Any]]:
        from framework1.database.ActiveRecord import bulk_preload_withs
        bulk_preload_withs(self, instance=instance)
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
