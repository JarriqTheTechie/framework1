import sqlite3
from dataclasses import dataclass
from typing import get_type_hints


# -------------------------
# Field Types
# -------------------------

class Field:
    def __init__(self, sql_type: str):
        self.sql_type = sql_type

    def __str__(self):
        return self.sql_type

class Varchar(Field):
    def __init__(self, length=255):
        super().__init__(f"VARCHAR({length})")

class Text(Field):
    def __init__(self):
        super().__init__("TEXT")

class Decimal(Field):
    def __init__(self, precision=18, scale=6):
        super().__init__(f"DECIMAL({precision}, {scale})")


# -------------------------
# ORM Core
# -------------------------

class ModelMeta(type):
    PYTHON_TO_SQL = {
        int: "BIGINT",
        str: "VARCHAR(255)",
        float: "DECIMAL(18, 6)",
        bool: "BOOLEAN"
    }

    def __new__(cls, name, bases, dct):
        new_cls = super().__new__(cls, name, bases, dct)
        annotations = get_type_hints(new_cls)
        mapping = {}

        for field, annotation in annotations.items():
            if isinstance(annotation, Field):
                sql_type = str(annotation)
            else:
                sql_type = cls.PYTHON_TO_SQL.get(annotation, "VARCHAR(255)")

            if field == "id" and sql_type == "BIGINT":
                sql_type = "INTEGER PRIMARY KEY AUTOINCREMENT"

            mapping[field] = sql_type

        new_cls.__mapping__ = mapping
        new_cls.__table__ = dct.get('__table__', name.lower())

        # Auto-generate __init__ if not defined
        if '__init__' not in dct:
            def __init__(self, **kwargs):
                for key in annotations:
                    setattr(self, key, kwargs.get(key, None))
            setattr(new_cls, '__init__', __init__)

        return new_cls


class Model(metaclass=ModelMeta):
    __session__ = None  # Injected at runtime

    def save(self):
        if not self.__session__:
            raise RuntimeError("Session not set on model")
        self.__session__.add(self)
        self.__session__.commit()

    @classmethod
    def get(cls, id):
        if not cls.__session__:
            raise RuntimeError("Session not set on model")
        return cls.__session__.get(cls, id)


class Mapper:
    def __init__(self, model_cls, conn):
        self.model_cls = model_cls
        self.conn = conn
        self.table = model_cls.__table__
        self.columns = list(model_cls.__mapping__.keys())

    def create_table(self):
        cols = ", ".join(f"{k} {v}" for k, v in self.model_cls.__mapping__.items())
        self.conn.execute(f"CREATE TABLE IF NOT EXISTS {self.table} ({cols})")

    def insert(self, obj):
        fields = [f for f in self.columns if f != 'id']
        placeholders = ', '.join(['?'] * len(fields))
        sql = f"INSERT INTO {self.table} ({', '.join(fields)}) VALUES ({placeholders})"
        values = [getattr(obj, f) for f in fields]
        cursor = self.conn.execute(sql, values)
        obj.id = cursor.lastrowid

    def get(self, id):
        sql = f"SELECT * FROM {self.table} WHERE id = ?"
        row = self.conn.execute(sql, (id,)).fetchone()
        if not row:
            return None
        return self.model_cls(**dict(zip(self.columns, row)))


class Session:
    def __init__(self, conn):
        self.conn = conn
        self.mappers = {}

    def register(self, model_cls):
        mapper = Mapper(model_cls, self.conn)
        self.mappers[model_cls] = mapper
        try:
            mapper.create_table()
        except Exception as e:
            print(f"Error creating table for {model_cls.__name__}: {e}")
        model_cls.__session__ = self

    def add(self, obj):
        mapper = self.mappers[type(obj)]
        mapper.insert(obj)

    def get(self, model_cls, id):
        return self.mappers[model_cls].get(id)

    def commit(self):
        self.conn.commit()


# -------------------------
# Example Usage
# -------------------------

if __name__ == "__main__":
    conn = sqlite3.connect(":memory:")
    session = Session(conn)


    @dataclass
    class LogEntry(Model):
        id: int
        title: str
        metadata: Varchar(1000)
        body: Text()
        score: Decimal(10, 4)
        is_valid: bool

    session.register(LogEntry)

    entry = LogEntry(title="System Init", metadata="init", body="This is a long message", score=9.5, is_valid=True)
    entry.save()

    fetched = LogEntry.get(entry.id)
    print(f"Fetched: {fetched.title} - score={fetched.score}, valid={fetched.is_valid}")
