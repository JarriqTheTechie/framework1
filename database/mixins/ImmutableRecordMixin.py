class ImmutableRecordMixin:
    """
    Make an ActiveRecord subclass effectively read-only.

    - Blocks save/create (unless explicitly allowed).
    - Blocks update/delete.
    - Uses lifecycle hooks so bulk operations with .with_events() also fail.

    To allow one-time creation but prevent later mutation, set
    `immutable_create_allowed = True` on the model and call `super().save(...)`
    only during seeding/bootstrapping.
    """

    immutable_create_allowed: bool = False
    immutable_reason: str = "immutable record (read-only)"

    # Lifecycle hooks
    def creating(self, *args, **kwargs):
        if not self.immutable_create_allowed:
            raise ValueError(f"{self.__class__.__name__} is {self.immutable_reason}: create blocked")

    def updating(self, *args, **kwargs):
        raise ValueError(f"{self.__class__.__name__} is {self.immutable_reason}: update blocked")

    def deleting(self, *args, **kwargs):
        raise ValueError(f"{self.__class__.__name__} is {self.immutable_reason}: delete blocked")

    # Direct operations (cover non-event paths)
    def save(self, *args, **kwargs):
        if not self.immutable_create_allowed:
            raise ValueError(f"{self.__class__.__name__} is {self.immutable_reason}: save blocked")
        return super().save(*args, **kwargs)

    def update(self, values=None, **kwargs):
        raise ValueError(f"{self.__class__.__name__} is {self.immutable_reason}: update blocked")

    def delete(self):
        raise ValueError(f"{self.__class__.__name__} is {self.immutable_reason}: delete blocked")


def ReadOnly(cls):
    """
    Class decorator to apply ImmutableRecordMixin without worrying about base-class order.

    Usage:
        @ReadOnly
        class Foo(ActiveRecord):
            ...
    """
    bases = (ImmutableRecordMixin, *cls.__bases__)
    attrs = dict(cls.__dict__)
    # Remove __dict__/__weakref__ if present to avoid duplication errors
    attrs.pop('__dict__', None)
    attrs.pop('__weakref__', None)
    readonly_cls = type(cls.__name__, bases, attrs)
    readonly_cls.__module__ = cls.__module__
    readonly_cls.__doc__ = cls.__doc__
    return readonly_cls
