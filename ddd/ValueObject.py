class ValueObject:
    """Base class for value objects with immutability and equality by value."""
    def __init__(self, value):
        self._value = self.validate(value)

    def validate(self, value):
        """Override in subclasses to enforce rules."""
        return value

    def __str__(self):
        return str(self._value)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self._value == other._value

    def __hash__(self):
        return hash((self.__class__, self._value))

    @property
    def value(self):
        return self._value
