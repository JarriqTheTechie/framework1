from pprint import pformat
import json
from datetime import datetime
from copy import deepcopy


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
            if isinstance(value, datetime):
                return value.isoformat()
            return value

        return {k: convert(v) for k, v in self._data.items()}

    def update(self, new_data):
        """Shallow update (like dict.update)."""
        self._data.update(new_data)

    def merge(self, new_data):
        """
        Deep merge dictionaries into the current DataKlass.
        Preserves existing nested keys instead of overwriting whole dicts.
        """

        def deep_merge(a, b):
            if isinstance(a, dict) and isinstance(b, dict):
                merged = deepcopy(a)
                for k, v in b.items():
                    if k in merged:
                        merged[k] = deep_merge(merged[k], v)
                    else:
                        merged[k] = deepcopy(v)
                return merged
            elif isinstance(a, DataKlass) and isinstance(b, (dict, DataKlass)):
                return DataKlass(deep_merge(a.to_dict(),
                                            b.to_dict() if isinstance(b, DataKlass) else b))
            elif isinstance(a, list) and isinstance(b, list):
                return a + b  # simple strategy: extend list
            else:
                return deepcopy(b)

        self._data = deep_merge(self._data, new_data._data if isinstance(new_data, DataKlass) else new_data)

    # --- JSON friendliness ---
    def __iter__(self):
        """Allow json.dumps() to treat this like a dict automatically."""
        return iter(self.to_dict().items())

    def __json__(self):
        """Some serializers (e.g. orjson, ujson) look for __json__."""
        return self.to_dict()

    # --- Comparisons & hashing ---
    def __eq__(self, other):
        if isinstance(other, DataKlass):
            return self.to_dict() == other.to_dict()
        if isinstance(other, dict):
            return self.to_dict() == other
        return False

    def __lt__(self, other):
        if isinstance(other, DataKlass):
            return self.to_dict() < other.to_dict()
        raise TypeError(f"'<' not supported between {type(self)} and {type(other)}")

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        if isinstance(other, DataKlass):
            return self.to_dict() > other.to_dict()
        raise TypeError(f"'>' not supported between {type(self)} and {type(other)}")

    def __ge__(self, other):
        return self == other or self > other

    def __hash__(self):
        # Serialize to immutable tuple for hashing
        return hash(json.dumps(self.to_dict(), sort_keys=True))

    # --- Cloning ---
    def clone(self):
        """Return a deep copy of this DataKlass."""
        return DataKlass(deepcopy(self._data), safe_mode=self._safe_mode)

    # --- Representation ---
    def __repr__(self):
        return f"{self.__class__.__name__}({pformat(self.to_dict(), indent=2, width=100)})"

    def __str__(self):
        return pformat(self.to_dict(), indent=2, width=100)

    # --- Debugging ---
    def dd(self):
        raise Exception(pformat(self.to_dict(), indent=2, width=100))