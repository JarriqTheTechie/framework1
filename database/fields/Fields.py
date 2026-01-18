from typing import Any, Optional, Union
from datetime import datetime, date, time
from decimal import Decimal


class Field:
    def __init__(
        self,
        primary_key: bool = False,
        nullable: bool = True,
        unique: bool = False,
        default: Any = None,
        index: bool = False,
        comment: str = None,
        collation: str = None,
    ):
        self.primary_key = primary_key
        self.nullable = nullable
        self.unique = unique
        self.default = default
        self.index = index
        self.comment = comment
        self.collation = collation

    # ----------------------------
    # Descriptor interface
    # ----------------------------
    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return instance.__data__.get(self.name, self.default)

    def __set__(self, instance, value):
        instance.__data__[self.name] = value

    def get_sql_type(self) -> str:
        raise NotImplementedError("Subclasses must implement get_sql_type()")



class IntegerField(Field):
    def __init__(self, auto_increment: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.auto_increment = auto_increment

    def get_sql_type(self) -> str:
        base_type = "INTEGER"
        return base_type


class BigIntegerField(IntegerField):
    def get_sql_type(self) -> str:
        base_type = "BIGINT"
        return base_type


class SmallIntegerField(IntegerField):
    def get_sql_type(self) -> str:
        base_type = "SMALLINT"
        return base_type


class CharField(Field):
    def __init__(self, max_length: int = 255, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length

    def get_sql_type(self) -> str:
        return f"VARCHAR({self.max_length})"




class TextField(Field):
    def get_sql_type(self) -> str:
        return "TEXT"


class DecimalField(Field):
    def __init__(self, precision: int = 10, scale: int = 2, **kwargs):
        super().__init__(**kwargs)
        self.precision = precision
        self.scale = scale

    def get_sql_type(self) -> str:
        return f"DECIMAL({self.precision},{self.scale})"


class BooleanField(Field):
    def get_sql_type(self) -> str:
        return "BOOLEAN"


class DateTimeField(Field):
    def __init__(self, auto_now: bool = False, auto_now_add: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add

    def __set__(self, instance, value):
        from datetime import datetime, date
        if isinstance(value, date) and not isinstance(value, datetime):
            value = datetime.combine(value, datetime.min.time())
        elif isinstance(value, str):
            value = datetime.fromisoformat(value)
        super().__set__(instance, value)

    def get_sql_type(self) -> str:
        return "DATETIME"


class DateField(Field):
    def __init__(self, auto_now: bool = False, auto_now_add: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add

    def __set__(self, instance, value):
        if isinstance(value, datetime):
            value = value.date()
        elif isinstance(value, str):
            value = datetime.fromisoformat(value).date()
        super().__set__(instance, value)

    def get_sql_type(self) -> str:
        return "DATE"


class TimeField(Field):
    def get_sql_type(self) -> str:
        return "TIME"


class JsonField(Field):
    def get_sql_type(self) -> str:
        return "JSON"

class MSSQLJsonField(Field):
    def get_sql_type(self) -> str:
        return "NVARCHAR(MAX)"


class MSSQLTimestampField(Field):
    def __init__(self, auto_update: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.auto_update = auto_update

    def get_sql_type(self) -> str:
        if self.auto_update:
            return "DATETIME2 DEFAULT SYSUTCDATETIME()"
        return "DATETIME2"
    
class MSSQLBooleanField(Field):
    def get_sql_type(self) -> str:
        return "BIT"

class BinaryField(Field):
    def __init__(self, max_length: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length

    def get_sql_type(self) -> str:
        if self.max_length:
            return f"BINARY({self.max_length})"
        return "BLOB"


class EnumField(Field):
    def __init__(self, choices: list[str], **kwargs):
        super().__init__(**kwargs)
        self.choices = choices

    def get_sql_type(self) -> str:
        choices_str = ", ".join(f"'{choice}'" for choice in self.choices)
        return f"ENUM({choices_str})"


class FloatField(Field):
    def get_sql_type(self) -> str:
        return "FLOAT"


class DoubleField(Field):
    def get_sql_type(self) -> str:
        return "DOUBLE"


class UUIDField(Field):
    def get_sql_type(self) -> str:
        return "CHAR(36)"


class IPAddressField(Field):
    def get_sql_type(self) -> str:
        return "VARCHAR(45)"  # Supports both IPv4 and IPv6


class URLField(CharField):
    def __init__(self, **kwargs):
        super().__init__(max_length=2083, **kwargs)  # Maximum URL length supported by IE


class EmailField(CharField):
    def __init__(self, **kwargs):
        super().__init__(max_length=254, **kwargs)  # Maximum email length per RFC 5321


class ForeignKeyField(Field):
    def __init__(self, to_table: str, to_column: str = "id",
                 on_delete: str = "CASCADE", **kwargs):
        super().__init__(**kwargs)
        self.to_table = to_table
        self.to_column = to_column
        self.on_delete = on_delete

    def get_sql_type(self) -> str:
        base_type = "INTEGER"  # Usually foreign keys are integers
        return f"{base_type}, FOREIGN KEY REFERENCES {self.to_table}({self.to_column}) ON DELETE {self.on_delete}"


class TimestampField(Field):
    def __init__(self, auto_update: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.auto_update = auto_update

    def get_sql_type(self) -> str:
        if self.auto_update:
            return "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        return "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
