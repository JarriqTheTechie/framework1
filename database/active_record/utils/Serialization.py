import pprint

from datetime import datetime
from framework1.utilities.DataKlass import DataKlass
from typing import Any

class ActiveRecordUtilitiesSerialization:
    def to_dict(self) -> DataKlass:
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

        # Serialize preloaded relationships
        if hasattr(self, "__with__"):
            for name in getattr(self, "__with__", []):
                cache_attr = f"_{name}_cache"
                if hasattr(self, cache_attr):
                    cached = getattr(self, cache_attr)
                    if isinstance(cached, ActiveRecord):
                        data[name] = cached.to_dict()
                    elif isinstance(cached, list):
                        data[name] = [c.to_dict() for c in cached]
                    else:
                        #raise Exception(f"Unexpected type for preloaded relationship '{name}': {type(cached)}")
                        data[name] = None

        return DataKlass(data)