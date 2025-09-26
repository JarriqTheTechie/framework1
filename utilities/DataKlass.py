from pprint import pformat


class DataKlass:
    def __init__(self, initial_data=None, safe_mode=False):
        self._data = initial_data or {}
        self._safe_mode = safe_mode

    def __getattr__(self, key):
        if key in self._data:
            return self._data[key]
        if self._safe_mode:
            return None
        raise AttributeError(f"{self.__class__.__name__} object has no attribute '{key}'")

    def __setattr__(self, key, value):
        if key in ("_data", "_safe_mode"):
            super().__setattr__(key, value)
        else:
            self._data[key] = value

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def __delattr__(self, key):
        if key in self._data:
            del self._data[key]
        else:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}'")

    def __delitem__(self, key):
        del self._data[key]

    def __contains__(self, key):
        return key in self._data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def safe_getattr(self, path, default=None):
        """
        Safe nested attribute getter.
        Example: safe_getattr("foo.bar.baz")
        """
        keys = path.split(".")
        current = self
        for key in keys:
            if isinstance(current, DataKlass):
                current = current._data.get(key, default)
            elif isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
            if current is None:
                return default
        return current

    def to_dict(self):
        """Recursively convert DataKlass into dicts."""
        def convert(value):
            if isinstance(value, DataKlass):
                return value.to_dict()
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [convert(v) for v in value]
            return value

        return {k: convert(v) for k, v in self._data.items()}

    def update(self, new_data):
        self._data.update(new_data)

    def __repr__(self):
        return f"{self.__class__.__name__}({pformat(self.to_dict(), indent=2, width=100)})"

    def __str__(self):
        return pformat(self.to_dict(), indent=2, width=100)
