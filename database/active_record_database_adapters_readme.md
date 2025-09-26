# Framework1 ActiveRecord & Database Adapters

A lightweight, fluent, ActiveRecord-style ORM for Python with cross‑database query building (MySQL & SQL Server), lifecycle events, relationship helpers, pagination, bulk inserts/upserts, and pragmatic utilities for schema introspection and serialization.

This guide covers:

- How to wire up database adapters (MySQL, MSSQL)
- Defining models and fields
- Querying data with a fluent builder
- CRUD (create, read, update, delete) via ActiveRecord
- Relationships (`belongs_to`, `has_many`) and serialization
- Events and scopes
- Pagination, bulk ops, upserts
- Debugging & raw SQL
- Schema utilities (generate/print table & forms)
- Best practices & edge cases

> **Files referenced**: `ActiveRecord.py`, adapters: `MySqlDatabase.py`, `MSSQLDatabase.py`, core protocol `Database.py`, query builder `QueryBuilder.py`, CRUD mixins (`Create.py`, `Read.py`, `Update.py`, `Delete.py`), utilities (`Int.py`, `Ext.py`, `Serialization.py`, `Schema.py`, `ModelCollection.py`), events (`decorators.py`).

---

## 1) Installation & Setup

### 1.1. Install driver dependencies

- **MySQL**: `mysql-connector-python`
- **SQL Server**: `pyodbc` and a Microsoft ODBC driver (e.g., *ODBC Driver 17 for SQL Server*)

```bash
pip install mysql-connector-python pyodbc
```

### 1.2. Create your adapter classes

Adapters subclass the provided `MySqlDatabase` / `MSSQLDatabase` and define connection details.

**MySQL**

```python
# databases.py
from framework1.core_services.MySqlDatabase import MySqlDatabase

class AppMySQL(MySqlDatabase):
    # Preferred: dict style
    connection_dict = {
        "user": "root",
        "password": "secret",
        "host": "127.0.0.1",
        "database": "app_db",
        "port": 3306,
    }
```

**SQL Server**

```python
# databases.py
from framework1.core_services.MSSQLDatabase import MSSQLDatabase

class AppMSSQL(MSSQLDatabase):
    # ODBC connection string
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost;PORT=1433;"
        "DATABASE=AppDb;"
        "Trusted_Connection=yes;"
        "Connection Timeout=10;"
    )
```

> **Tip**: Use environment variables or a central settings module to keep credentials out of source control.

---

## 2) Define Models

A model subclasses `ActiveRecord` and declares its table, primary key, database adapter, and driver.

```python
# models.py
from framework1.database.ActiveRecord import ActiveRecord
from databases import AppMySQL, AppMSSQL

class User(ActiveRecord):
    __table__ = "users"
    __primary_key__ = "id"
    __database__ = AppMySQL   # or AppMSSQL
    __driver__ = "mysql"      # "mysql" or "mssql"
```

> You can declare "fields" using the `framework1.database.fields.Fields` system and auto‑generate DDL with `Schema` utilities (see §11). The ORM itself does not require field declarations to operate.

### 2.1. Appended (computed) attributes

Add computed attributes to serialized output by listing them in `__appends__` and implementing `get_<name>_attribute()`:

```python
class User(ActiveRecord):
    __table__ = "users"
    __database__ = AppMySQL
    __driver__ = "mysql"
    __appends__ = ["full_name"]

    def get_full_name_attribute(self):
        return f"{self.__data__.get('first_name','')} {self.__data__.get('last_name','')}".strip()
```

---

## 3) Quick Start (CRUD)

### Create

```python
# Via classmethod
u = User.create(first_name="Ada", last_name="Lovelace", email="ada@example.com")

# Or build + save
u = User(first_name="Ada", last_name="Lovelace").save()
```

Under the hood, inserts add `created_at` & `updated_at` timestamps. MySQL uses `cursor.lastrowid`; MSSQL uses `SCOPE_IDENTITY()` to populate the primary key.

### Read

```python
# Find by primary key
u = User().find(1)              # -> User or None

# Find first matching
u = User().find_by('email', 'ada@example.com')

# All
users = User().all()            # -> ModelCollection[User]

# Take N (no order)
User().take(5)                  # -> list[User]

# First/Last by primary key
User().first()                  # -> User or None
User().last(5)                  # -> list[User]

# Strict variants (raise RecordNotFound)
User().first_strict()
User().last_strict()
User().take_strict()
```

### Update

```python
# Instance update (safe, fires events)
u = User().find(1)
u.update({"last_name": "Byron"})

# Bulk update with WHERE (no instance hydration)
User().where("role", "=", "guest").update({"role": "user"})

# With events for each row (hydration cost)
User().with_events().where("status", "=", "pending").update({"status": "active"})
```

> The builder protects you from unsafe updates: `UPDATE` requires a `WHERE` clause. Instance updates ignore primary key in the payload.

### Delete

```python
# Delete by ID, returns affected rows
User().delete(1)

# Delete by query (bulk)
User().where("status", "=", "inactive").delete()

# From a found instance: returns the hydrated instance on success
u = User().find(5)
deleted = u.delete()  # -> User instance
```

---

## 4) Fluent Query Builder Essentials

The `ActiveRecord` base inherits a full‑featured `QueryBuilder`. Common patterns:

```python
# Basic selects
User().select("id", "email").where("active", "=", 1).order_by("id", "DESC").limit(10).all()

# Where dictionary shorthand
User().where({"active": 1, "role": "user"}).all()

# IN / BETWEEN / NULLs
User().where_in("id", [1,2,3]).all()
User().where_between("created_at", "2024-01-01", "2024-12-31").all()
User().where_null("deleted_at").all()

# LIKE
User().where_like("email", "%@example.com")

# Date helpers (database-agnostic)
User().where_date("created_at", "=", "2025-08-10")
User().where_today("created_at")

# Nesting ( (a AND b) OR (c AND d) )
User().nest(lambda q: q.where("role", "=", "user").where("active", "=", 1)) \
     .or_nest(lambda q: q.where("role", "=", "admin").where("status", "=", "invited"))

# Joins / Raw
User().join("profiles p", "users.id", "=", "p.user_id")
User().where_raw("users.deleted_at IS NULL")

# Pagination (DB-level LIMIT/OFFSET or OFFSET/FETCH)
page = User().order_by("id").paginate(page=2, per_page=25)
page.items            # ModelCollection[User]
page.to_dict()        # JSON‑friendly payload
```

### Driver differences handled for you

- Placeholders: MySQL uses `%s`; MSSQL uses `?` internally in the adapter. You write builder code once.
- Quoting: backticks for MySQL, brackets for MSSQL.
- Pagination on MSSQL requires an `ORDER BY`; the builder will enforce/expect this.

### Dynamic convenience methods

```python
User().where_email("ada@example.com")        # -> where("email", "=", …)
User().find_by_email("ada@example.com")     # -> find_by("email", …)
User().where_in_id([1,2,3])                  # -> where_in("id", …)
User().where_null_deleted_at()               # -> where_null("deleted_at")
```

---

## 5) Relationships

Two helpers are provided for common patterns:

```python
class Post(ActiveRecord):
    __table__ = "posts"
    __database__ = AppMySQL
    __driver__ = "mysql"

    # belongs_to(User, match_on=local_fk, match_with=remote_pk)
    def author(self):
        return self.belongs_to(User, match_on="user_id", match_with="id")

class Comment(ActiveRecord):
    __table__ = "comments"
    __database__ = AppMySQL
    __driver__ = "mysql"

class Post(ActiveRecord):
    # has_many(Comment, match_on=local_pk, match_with=remote_fk)
    def comments(self):
        return self.has_many(Comment, match_on="id", match_with="post_id")
```

**Lazy first access, batched subsequent queries**

- The first relationship access runs the minimal query.
- When serializing many records, the system batches relationship queries per database using `pquery()` for efficiency (see §6 and §10).

> **Note**: Batched serialization infers mapping keys. Ensure your foreign keys follow the conventional pattern you pass into `has_many` / `belongs_to`. If you customize key names heavily, prefer manual composition or single‑record `serialize()` calls.

---

## 6) Serialization

```python
post = Post().find(1)
post.serialize()                  # nested relationships (depth=3 default)
post.serialize(depth=1)           # shallower
post.serialize(include=["id", "title", "author"])   # limit fields

posts = Post().where({"status": "pub"}).all()
posts.serialize(depth=2)          # efficient batch loading

# Plain dict without relationship expansion
post.to_dict()
```

Serialization converts `datetime` to ISO‑8601, encodes `bytes` as Base64, expands nested ActiveRecord instances and lists, and appends any `__appends__` getters.

---

## 7) Events

Register event listeners using the `@on` decorator. Supported events include: `creating`, `created`, `saving`, `saved`, `updating`, `updated`, `retrieved`, `deleting`, `deleted`.

```python
from framework1.database.active_record.decorators import on

class User(ActiveRecord):
    __table__ = "users"
    __database__ = AppMySQL
    __driver__ = "mysql"

    @on("creating")
    def ensure_unique_email(self):
        # simple example (for demo only)
        if User().find_by("email", self.__data__["email"]):
            raise ValueError("Email already taken")

    @on("retrieved")
    def hydrate_flags(self):
        self.__data__["is_admin"] = (self.__data__.get("role") == "admin")
```

For bulk `update()`/`delete()`, use `.with_events()` to hydrate and fire per‑instance events—trading performance for hooks.

---

## 8) Scopes

Scopes are collected from base classes whose names end with `Scope` and implement `apply(self)`.

```python
class TenantScope:
    @staticmethod
    def apply(q):
        from framework1.core_services.Request import Request
        tenant = Request().session().get("TenantId")
        if tenant:
            q.where("TenantId", "=", tenant)

class Payment(ActiveRecord, TenantScope):
    __table__ = "payment"
    __database__ = AppMSSQL
    __driver__ = "mssql"

# Disable all scopes, or selectively exclude
Payment().without_scopes()                # disable all
Payment().without_scopes(["TenantScope"])  # keep others
```

You can also manually re‑enable scopes via `.with_scopes(...)`.

---

## 9) Pagination

Database‑level pagination returns a convenient `PaginationResult`:

```python
page = User().order_by("id").paginate(page=3, per_page=20)
page.items        # ModelCollection[User]
page.total        # total rows
page.has_next     # etc.
page.to_dict()    # JSON‑ready payload
```

- MySQL uses `LIMIT %s OFFSET %s` parameters.
- MSSQL uses `ORDER BY … OFFSET %s ROWS FETCH NEXT %s ROWS ONLY` and **requires** an `ORDER BY` clause.

---

## 10) Bulk Ops, Upserts, and Batched Queries

### 10.1. Insert many

```python
rows = [
    {"email": "a@x.com", "role": "user"},
    {"email": "b@x.com", "role": "admin"},
]
sql, params = User().insert_many(rows)
User().db.query(sql, params)
```

### 10.2. Upsert / update\_or\_insert

```python
# MySQL: ON DUPLICATE KEY; MSSQL: MERGE
sql, params = User().upsert(
    rows=[{"email": "a@x.com", "role": "user"}],
    unique_by=["email"],
    update_columns=["role"],
)
User().db.query(sql, params)
```

### 10.3. Adapter `pquery()` (multi‑result batching)

Both adapters support `pquery()`—executing multiple SELECTs in one round‑trip and returning a list of named resultsets:

```python
adapter = AppMySQL()
resultsets = adapter.pquery([
    {"users": User().select("*").where("active", 1)},
    {"admins": User().select("*").where("role", "admin")},
])
# -> [{"users": [DotDict, …]}, {"admins": [DotDict, …]}]
```

This is used internally for batched relationship loads during `serialize_many()`.

---

## 11) Schema Utilities (optional but handy)

The `Schema` mixin provides conveniences for generating table DDL and printing scaffolds from a live database.

```python
# Generate CREATE TABLE DDL from declared Field()s
print(User.generate_schema())
User.create_table()  # executes the DDL against __database__

# Introspect a live table (driver-aware) and print a model skeleton
print(User().print_model())

# Generate simple Table/Form scaffolds (for the DSL layer)
print(User().print_table())
print(User().print_form())
```

> These helpers target MySQL and MSSQL; PostgreSQL is partially scaffolded in the code for `get_table_fields()` but not otherwise supported by adapters.

---

## 12) Debugging & Raw SQL

```python
# View SQL with parameters substituted
User().where("email", "=", "a@x.com").dump_raw_sql()

# Explain plan (MySQL only)
User().where("active", 1).explain()

# Hard stop with SQL shown
User().dd_sql()

# Get the final SQL/params
sql, params = User().get()
```

Log output is handled by `orm.debug` logger (see `Logging.py`).

---

## 13) Transactions (MySQL adapter convenience)

MySQL adapter exposes a context manager for transactions:

```python
from databases import AppMySQL

db = AppMySQL()

try:
    with db.transaction():
        User().create(email="x@x.com")
        # do more work
except Exception:
    # rolled back automatically; exception propagated
    raise
```

For MSSQL, use the connection obtained via `db.connect()` and call `commit()` / `rollback()` as needed.

---

## 14) Best Practices

1. **Always set **``** and **``** on each model.** The builder tailors SQL (placeholders/quoting/pagination) based on the driver.
2. **Use instance updates for single rows; bulk updates for sets.** Instance updates fire events and maintain internal state; bulk updates are faster but skip per‑row hooks unless you opt into `.with_events()`.
3. **Guard dangerous writes.** The builder refuses `UPDATE` without a `WHERE`. Use tight predicates and review `.dump_raw_sql()` in tests.
4. **Paginate with ORDER BY on MSSQL.** The builder enforces/assumes this; add an explicit `.order_by()` before `.paginate()`.
5. **Prefer batched serialization for lists.** `ModelCollection.serialize()` batches relationship queries across records and databases, minimizing N+1s.
6. **Keep relationships conventional.** Use clear foreign keys (e.g., `post_id`). If conventions drift, serialize one record at a time or manually join.
7. **Wrap multi‑step writes in transactions.** Especially when mixing create/update across multiple tables.
8. **Use events for business invariants, not for heavy I/O.** Keep listeners fast; push slow tasks to queues/background jobs.
9. **Log and test generated SQL.** `.dump_raw_sql()` is your friend—include it in unit tests for tricky queries.
10. **Catch **``** where you opt into strict reads.** Return 404s or user‑friendly messages accordingly.

---

## 15) Edge Cases & Limitations

- **Missing primary key**: The default `__primary_key__` is `id`. If your PK differs, set `__primary_key__` on the model. Instance updates will strip the PK from the update payload.
- **Find returns **``: `find()`/`find_by()` may return `None`; use strict variants to raise.
- **Delete return type**: Deleting via a found instance returns the deleted instance; direct `delete(id)`/bulk returns affected row count.
- **MSSQL pagination requires order**: Attempting `.paginate()` without an `ORDER BY` on MSSQL raises `ValueError`.
- **Upserts require driver support**: Implemented for MySQL (`ON DUPLICATE KEY`) and MSSQL (`MERGE`).
- ``: Uses `EXPLAIN` prefix; primarily for MySQL. MSSQL users should run execution plans via SSMS.
- ``** argument counts**: When batching multiple queries, ensure the total number of `%s` placeholders matches the supplied parameters (MySQL adapter compensates for simple single-arg cases, but prefer explicitness).
- **Relationship batching assumptions**: `serialize_many()` currently infers mapping keys and may expect conventional names (e.g., `<model>_id`). If your schema diverges, consider per‑record `serialize()` or customizing the batching behavior.
- **Bytes columns**: Serialized to Base64 for JSON; be aware of payload size.
- **Events with bulk ops**: `.with_events()` hydrates rows, which can be expensive for large sets.

---

## 16) Worked Examples

### 16.1. Simple report with filters

```python
q = User().select("id", "email", "role").where({"active": 1})
q = q.or_where_like("email", "%@example.com")
rows = q.order_by("id", "DESC").limit(50).all()
for u in rows:
    print(u.to_dict())
```

### 16.2. Admins with recent posts (join + pagination)

```python
posts = (
    Post()
      .select("p.id", "p.title", "u.email AS author_email")
      .table("posts", alias="p")
      .join("users u", "p.user_id", "=", "u.id")
      .where("u.role", "=", "admin")
      .order_by("p.id", "DESC")
      .paginate(page=1, per_page=20)
)
print(posts.to_dict())
```

### 16.3. Upsert from a feed

```python
rows = [
  {"email": "m@x.com", "role": "user"},
  {"email": "a@x.com", "role": "admin"},
]
sql, params = User().upsert(rows, unique_by=["email"], update_columns=["role"])
User().db.query(sql, params)
```

---

## 17) Reference Cheatsheet

- **Model lifecycle**: `create()` → (creating, saving) → INSERT → (created, saved)

  Instance update: (updating, saving) → UPDATE → (updated, saved)

- **Collections**: `ModelCollection` adds `to_list_dict()`, `serialize()`, `pluck()`, `where()` (filter), `first()`, `last()`.

- **Raw SQL**: `raw_sql()`, `dump_sql()`, `dump_raw_sql()`, `dd_sql()`, `get()`

- **Safety**: `update()` without `WHERE` raises; PK stripped from update payload.

- **Adapter conveniences**:

  - MySQL: `.transaction()` context manager
  - Both: `.pquery()` for batched selects

---

## 18) Minimal Model Template

```python
from framework1.database.ActiveRecord import ActiveRecord
from databases import AppMySQL

class Widget(ActiveRecord):
    __table__ = "widgets"
    __primary_key__ = "id"
    __database__ = AppMySQL
    __driver__ = "mysql"
```

---

## 19) Troubleshooting

- **ProgrammingError / placeholder mismatch**: Ensure your `%s` placeholders match argument counts (especially when concatenating queries or using `pquery()`).
- ``: Add `.order_by()` before `.paginate()`.
- **No results / exceptions**: `find()` returns `None`; `*_strict()` raises `RecordNotFound`. The base `Database` protocol also exposes `results_or_fail()` raising `NoResultsFound` with optional fallback.
- **Connection errors**: Validate `connection_dict` (MySQL) or `connection_string` (MSSQL) and driver availability.

---

## 20) License & Contributions

This module is intended for internal use within Framework1 projects. Contributions via merge requests are welcome—please include unit tests covering SQL generation for both MySQL and MSSQL and verify event firing semantics.

