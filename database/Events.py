from typing import Callable
from typing import Optional
from typing import TypeVar, Type

from dataclasses import dataclass

@dataclass(frozen=True)
class DomainEvent:
    """Base class for domain events."""
    pass

T = TypeVar("T", bound="ActiveRecord")

class Events:
    __booted_classes__ = set()
    __event_listeners__ = {}

    @classmethod
    def boot(cls):
        if cls in cls.__booted_classes__:
            return

        if hasattr(cls, "booted") and callable(cls.booted):
            cls.booted()
        cls.__booted_classes__.add(cls)

    def with_events(self: T) -> T:
        """
        Enable lifecycle event firing for bulk operations (e.g., delete, update).
        """
        self._with_events = True
        return self

    @classmethod
    def on(cls, event_name: str, callback, priority: int = 0):
        """
        Register a class-level event listener for a specific event.

        Args:
            event_name (str): Name of the event (e.g., "created", "retrieved").
            callback (callable): Function to execute when the event is fired.
            priority (int, optional): Determines execution order. Higher runs first.
        """
        cls.__event_listeners__.setdefault(cls, {}).setdefault(event_name, [])

        # Prevent duplicate (priority, callback) pairs
        registered = cls.__event_listeners__[cls][event_name]
        if (priority, callback) not in registered:
            registered.append((priority, callback))
            # Sort by priority descending
            registered.sort(key=lambda pair: pair[0], reverse=True)

    def fire_event(self, event_name: str, instance=None):
        """
        Fire a lifecycle event, triggering both instance and class-level listeners.

        Args:
            event_name (str): The name of the event (e.g., 'created', 'retrieved').
            instance (ActiveRecord, optional): The model instance to pass to listeners.
        """
        target = instance or self

        # 1. Call instance method, e.g., instance.created()
        method = getattr(target, event_name, None)
        if callable(method):
            try:
                method()
            except Exception as e:
                print(f"Error in event '{event_name}' for {target.__class__.__name__}: {e}")

        # 2. Call class-level listeners (including global "__all__")
        listeners = (
                self.__class__.__event_listeners__
                .get(self.__class__, {})
                .get(event_name, [])
                +
                self.__class__.__event_listeners__
                .get(self.__class__, {})
                .get("__all__", [])
        )

        for _, callback in listeners:
            try:
                callback(target)
            except Exception as e:
                print(f"Error in class-level event '{event_name}' for {target.__class__.__name__}: {e}")

    # ----------------------------------------------------------------------
    # Lifecycle Events
    # ----------------------------------------------------------------------

    def retrieved(self, *args, **kwargs):
        """
        Event triggered after a record is retrieved from the database.
        """
        pass

    def creating(self, *args, **kwargs):
        """
        Event triggered before a record is created.
        This can be used to modify the model before saving.
        """
        pass

    def created(self, *args, **kwargs):
        """
        Event triggered after a record is created.
        """
        pass

    def updating(self, *args, **kwargs):
        """
        Event triggered before a record is updated.
        This can be used to modify the model before saving.
        """
        pass

    def updated(self, *args, **kwargs):
        """
        Event triggered after a record is updated.
        """
        pass

    def saving(self, *args, **kwargs):
        """
        Event triggered before a record is saved (either created or updated).
        This can be used to modify the model before saving.
        """
        pass

    def saved(self, *args, **kwargs):
        """
        Event triggered after a record is saved (either created or updated).
        """
        pass

    def deleting(self, *args, **kwargs):
        """
        Event triggered before a record is deleted.
        This can be used to perform checks or modifications before deletion.
        """
        pass

    def deleted(self, *args, **kwargs):
        """
        Event triggered after a record is deleted.
        This can be used to perform cleanup or logging after deletion.
        """
        pass

    # ----------------------------------------------------------------------
    # Domain Events
    # ----------------------------------------------------------------------
    @classmethod
    def subscribe_domain_event(cls, event_type: Type[DomainEvent], handler: Callable):
        """
        Subscribe a handler to a domain event.
        """
        cls.__domain_listeners__.setdefault(event_type, [])
        if handler not in cls.__domain_listeners__[event_type]:
            cls.__domain_listeners__[event_type].append(handler)

    @classmethod
    def publish_domain_event(cls, event: DomainEvent):
        """
        Publish a domain event to all subscribers.
        """
        listeners = cls.__domain_listeners__.get(type(event), [])
        for handler in listeners:
            try:
                handler(event)
            except Exception as e:
                print(f"[DomainEvent Error] {handler} failed: {e}")