# Framework1

A lightweight, batteries‑included layer on top of Flask that gives you:

- **App bootstrap** (service container, handler discovery, request lifecycle hooks)
- **Routing conventions** for flat `lib/handlers/**` modules or controller classes
- **Templating helpers** and safe template rendering
- **Ergonomic request helpers** (`Request`)
- **Database adapters** (MySQL, MSSQL) + a cross‑DB **QueryBuilder**
- **ActiveRecord‑style models** with CRUD, events, scopes, and serialization
- **Utility collections** and view props compaction

This guide covers practical usage, best‑practice patterns, and gotchas.

> The examples below are based **only** on what’s shipped in the code you installed.

---

## Table of contents

1. [Quick start](#quick-start)
2. [Project structure](#project-structure)
3. [Bootstrapping the app](#bootstrapping-the-app)
4. [Services and lifecycle hooks](#services-and-lifecycle-hooks)
5. [Handlers, controllers, and routing](#handlers-controllers-and-routing)
6. [Templating and helpers](#templating-and-helpers)
7. [Request helper](#request-helper)
8. [View props (](#view-props-viewprops)[`ViewProps`](#view-props-viewprops)[)](#view-props-viewprops)
9. [Database adapters](#database-adapters)
10. [QueryBuilder](#querybuilder)
11. [ActiveRecord models](#activerecord-models)
12. [CLI: ](#cli-flask-manage)[`flask manage`](#cli-flask-manage)
13. [Debugging](#debugging)
14. [Security notes](#security-notes)
15. [Edge cases & pitfalls](#edge-cases--pitfalls)

---

## Quick start

Install Framework1 into a Flask project and wire up the bootstrap.

```bash
pip install framework1  # or your local editable install
```

```python
# app.py
from flask import Flask
from framework1 import Framework1

app = Flask(__name__)

# Initialize Framework1 (service container, handlers, controllers, etc.)
Framework1(app, debug=True, services_path="lib/services")

if __name__ == "__main__":
    app.run(debug=True)
```

**Environment**

- Add a strong `APP_SECRET_KEY` in `.env` (Framework1 loads via `python-dotenv`).

```
APP_SECRET_KEY=base64:...super-secret...
```

**Folders you’ll typically use**

```
lib/
  handlers/        # your routes/views/controllers live here
  resources/       # static assets (served as /resources/*)
  services/        # container-registered singletons
```

---

## Project structure

Framework1 assumes a **convention-first** layout:

- **Handlers**: Python files under `lib/handlers/**`. You can write simple module-level routes (a `view()` function), or controller classes ending in `Controller`.
- **Static**: `lib/resources` becomes the Flask `static_folder`.
- **Templates**: Jinja loader points to `lib/handlers` so a handler can ship its own template next to the code.

---

## Bootstrapping the app

`framework1.__init__.Framework1(app, debug=False, services_path="lib/services")`:

- Loads env + secret key
- Initializes the **Service Container** (`init_container`) scanning your `services_path`
- Imports all `lib/handlers/**.py`
- Instantiates all `*Controller` classes (`discover_and_init_controllers`) and collects **navigation items**
- Configures Jinja loader + static folder
- Wires request lifecycle hooks (`before_request`, `after_request`, `teardown_request`)
- Registers useful Jinja globals/filters

> You can also manually call `discover_convention_routes(app)` if you prefer the “module with `view()` function” style of routing (see [Handlers & routing](#handlers-controllers-and-routing)).

**Best practice**

- Keep bootstrap in a single place (e.g., `app.py`).
- Pass `debug=True` while iterating on handler discovery so import errors surface clearly in the console.

---

## Services and lifecycle hooks

Any singleton that implements `LifecycleAware` can observe the request flow.

Lifecycle hook methods picked up automatically if your service is registered as a singleton in the container:

```python
class MyAuditService(LifecycleAware):
    def on_request_start(self, ctx):
        ...  # ctx: {path, method, headers}
    def on_request_exception(self, ctx):
        ...  # ctx: {exception, path, method, duration, status}
    def on_request_end(self, ctx):
        ...
    def on_response_sent(self, ctx):
        ...
```

**Registering a singleton service**

```python
# lib/services/audit.py
from framework1.service_container._Injector import singleton
from framework1.interfaces.LifecycleAware import LifecycleAware

@singleton
class AuditService(LifecycleAware):
    ...  # implement the methods above
```

> All container singletons are probed on each request; those implementing `LifecycleAware` get lifecycle callbacks.

**Best practice**

- Use lifecycle services for cross-cutting concerns: logging, tracing, request metrics, feature flags.
- Keep them **stateless** and **fast**; they run on every request.

---

## Handlers, controllers, and routing

### 1) Module-level route (convention routing)

Place a file anywhere under `lib/handlers/**`. Provide a callable `view()`.

```python
# lib/handlers/dashboard.py
from flask import render_template_string
from framework1 import discover_convention_routes

route = "/dashboard"          # optional; default derives from path
methods = ["GET", "POST"]      # optional; default ["GET"]

def view():
    return render_template_string("<h1>Dashboard</h1>")
```

Enable convention routing (once) after Framework1 boots:

```python
from framework1 import discover_convention_routes
...
Framework1(app, debug=True)
discover_convention_routes(app, debug=True)
```

### 2) Controller classes (auto‑instantiated)

Any class in `lib/handlers/**` whose name ends with `Controller` is instantiated at boot. If it exposes `GetNavigation()`, menu items are collected and injected into templates as `navigation`.

```python
# lib/handlers/home/HomeController.py
class HomeController:
    def GetNavigation(self):
        return [{
            "label": "Home",
            "href": "/",
            "icon": "ri-home-2-line",
            "weight": 1,
        }]
```

**Best practice**

- Keep controllers small; move heavy logic into services.
- Prefer **module routes** for simple pages; use **controllers** when you need DI, state, or nav aggregation.

---

## Templating and helpers

Framework1 exposes helpers to Jinja:

- `env(key)`: pull from environment
- Filters: `humanize_dt`, `split`, `safe_iter`, `json_load`, `PageTitle`
- Globals: `is_active(query_fragment)`, `current_path()`

```jinja
<h1>{{ 'APP_NAME'|env }}</h1>
<p>{{ some_iso_datetime|humanize_dt }}</p>
<nav>
  <ul>
    {% for item in navigation %}
      <li class="{{ is_active(item.href) }}">
        <a href="{{ item.href }}">{{ item.label }}</a>
      </li>
    {% endfor %}
  </ul>
</nav>
```

**Safe package templates**

Render installed package templates by path with `render_template_string_safe_internal(relative_path, **ctx)`.

```python
from framework1 import render_template_string_safe_internal

html = render_template_string_safe_internal("layout.html", title="Welcome")
```

**Best practice**

- Keep display logic in templates; pass only what’s needed using `ViewProps.compact()` (see next).

---

## Request helper

`framework1.core_services.Request.Request` streamlines access to query, form, JSON, files, and casting.

```python
from framework1.core_services.Request import Request
req = Request()

# Basic input
page = req.integer("page", 1)
q = req.string("q")
ids = req.to_list("ids[]", [], int)

# Dates & times (auto‑parse common formats)
start = req.date("start_date")
stamp = req.datetime_("stamp", tz="America/Nassau")   # returns UTC by default
when = req.time("when")

# Booleans
active = req.boolean("active", False)

# Grouped form inputs: mygroup[0][field] → list of dicts
rows = req.grouped(prefix="filters")

# Files
if req.has_file("avatar"):
    path = req.file("avatar").save(prefix="user", suffix="avatar")

# Validation (rule functions resolved by name)
errors = req.validate({
    "email": ["required", "email"],
    "age": [lambda k, v: None if (v and int(v) >= 18) else "must be 18+"],
})
if errors:
    ...
```

**Best practice**

- Use strong defaults and explicit casting (e.g., `integer`, `to_list(..., int)`).
- Use `csrf_token()` + `validate_csrf()` for sensitive POSTs.
- `flash_only()`/`old()` support sticky forms on validation errors.

---

## View props (`ViewProps`)

Compact the local variables of a view/controller method into a clean dict for the template or JSON.

```python
from framework1.core_services.ViewProps import ViewProps

def index():
    title = "Users"
    data = [{"id": 1, "name": "Ada"}]
    view_props = True  # any sentinel; removed by compact()
    return render_template_string("...", **ViewProps.compact())
```

API‑safe compaction with includes/excludes:

```python
payload = ViewProps.api_compact(exclude_keys=["secret"], include_keys=["data", "title"])  # optional filters
```

**Best practice**

- Set a local `view_props` sentinel and never pass it to templates; `compact()` removes it for you.
- Keep the local scope tidy; define only what you need to render.

---

## Database adapters

Two adapters implement the `Database` protocol: **MySQL** and **MSSQL**.

### Configure an adapter

Create your own typed adapter class and set credentials in code or env.

```python
# db.py
from framework1.core_services.database.MySqlDatabase import MySqlDatabase
from framework1.core_services.database.MSSQLDatabase import MSSQLDatabase

class AppMySQL(MySqlDatabase):
    connection_dict = {
        "host": "localhost",
        "user": "root",
        "password": "secret",
        "database": "appdb",
        "port": 3306,
    }

class AppMSSQL(MSSQLDatabase):
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost;PORT=1433;DATABASE=appdb;"
        "Trusted_Connection=yes;Connection Timeout=10;"
    )
```

### Running queries

Both adapters accept a **raw SQL string** or a **QueryBuilder** and return a list of dict‑like objects supporting dot access.

```python
rows = AppMySQL().query("SELECT * FROM users WHERE id=%s", 10)
for u in rows:
    print(u.id, u.name)
```

**Batch queries (**``**)**

```python
resultsets = AppMySQL().pquery([
  {"users": "SELECT id, name FROM users WHERE id IN (%s, %s)"},
  {"posts": "SELECT * FROM posts WHERE user_id IN (%s, %s)"},
], 1, 2, 1, 2)
```

**Saving**

```python
# Insert and return inserted row
row = AppMySQL().save("users", {"name": "Ada"})

# Update by where and return updated row(s) when supported
AppMSSQL().save("users", {"name": "Ada Lovelace"}, where={"id": 1})
```

**Transactions (MySQL)**

```python
with AppMySQL().transaction() as conn:
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET balance = balance - %s WHERE id=%s", (100, 1))
    cur.execute("UPDATE accounts SET balance = balance + %s WHERE id=%s", (100, 2))
```

**Best practice**

- Always **parameterize**; let the adapter replace placeholders (`%s` in MySQL, auto‑converted to `?` for MSSQL when needed).
- Prefer `QueryBuilder` for portability; avoid driver‑specific functions in SQL where possible.

---

## QueryBuilder

A fluent, cross‑DB query DSL that emits parameterized SQL. Set the driver for proper quoting and pagination behavior.

```python
from framework1.core_services.database.QueryBuilder import QueryBuilder

qb = (QueryBuilder()
      .set_driver("mysql")
      .table("users")
      .select("id", ("name", "label"))
      .where("active", "=", 1)
      .where_in("role", ["admin", "editor"])
      .order_by("id", "DESC")
      .limit(10)
      .offset(0))

sql, params = qb.get()
```

### Highlights

- `where` / `or_where` accept raw columns, subqueries, or `Raw(...)`
- Rich helpers: `where_between`, `where_like`, `where_null`, `where_date`, `where_month/day/year`, `where_full_text` (MySQL `MATCH`, MSSQL `CONTAINS`), `nest()/or_nest()`
- Joins: `join`, `left_join`, `join_raw`
- Aggregates: `group_by`, `having`
- Pagination: `paginate(page, per_page)` generates driver‑safe LIMIT/OFFSET or `OFFSET..FETCH` (requires `order_by` on MSSQL)
- Mutations: `insert`, `insert_many`, `update`, `delete`, `insert_get_id`, `insert_or_ignore`, `upsert`, `update_or_insert`
- Utilities: `dump()`, `dump_raw_sql()`, `dd()` (raises), `dd_raw_sql()` (raises), `raw_sql()`

**Updates**

```python
qb = (QueryBuilder().set_driver("mysql").table("users")
      .where("id", "=", 5))
sql, params = qb.update({"name": "Ada"})  # safe: requires WHERE
```

**Upserts**

```python
# MySQL: ON DUPLICATE KEY UPDATE / MSSQL: MERGE
sql, params = (QueryBuilder().set_driver("mssql").table("users")
               .upsert([
                   {"id": 1, "name": "Ada"},
                   {"id": 2, "name": "Grace"},
               ], unique_by=["id"], update_columns=["name"]))
```

**Best practice**

- Always call `.set_driver("mysql"|"mssql")` early for correct quoting.
- On MSSQL, set an explicit `.order_by(...)` before `.paginate(...)`.
- Use `Raw(...)` sparingly for functions/expressions you fully control.

---

## ActiveRecord models

Define models that combine `QueryBuilder` with CRUD, events, scopes, and serialization.

```python
# models.py
from framework1.core_services.database.ActiveRecord import ActiveRecord
from .db import AppMySQL

class User(ActiveRecord):
    __table__ = "users"
    __driver__ = "mysql"
    __database__ = AppMySQL
    __primary_key__ = "id"
```

### Reading

```python
User().where("active", 1).order_by("id", "DESC").all()     # → ModelCollection
User().find(10)                                                # → User | None
User().first()                                                 # first by PK
User().last(5)                                                 # last 5 by PK
User().paginate(page=1, per_page=20)                           # → PaginationResult
```

### Creating & saving

```python
# Mass-assign
u = User.create(name="Ada", active=1)    # fires creating/saving/created/saved

# Or build + save
u = User(name="Grace", active=1)
u.save()

# Bulk
created = User.create_bulk([
  {"name": "A"}, {"name": "B"}
])
```

### Updating

```python
u = User().find(1)
u.update({"name": "Updated"})          # instance path (fires updating/saving/updated/saved)

# Bulk update with a WHERE (fast path w/o events)
User().where("active", 0).update({"active": 1})
```

### Deleting

```python
# Delete by id and get affected count
count = User().where("active", 0).delete()

# Delete a found instance and get the deleted instance back
user = User().find(10)
removed = user.delete()     # returns the instance when deleting a loaded record
```

### Serialization

```python
u = User().find(1)
print(u.serialize(depth=0))     # include only the model’s own fields
print(u.to_dict())
```

> Note: Relationship helpers exist in code for batched loading, but if you are **not** using relationships, keep `depth=0` in `serialize()` for speed and clarity.

### Events

Attach event listeners with the `@on` decorator.

```python
from framework1.core_services.database.active_record.decorators import on

class User(ActiveRecord):
    ...

    @on("saving", priority=10)
    def validate_name(self):
        if not self.name:
            raise ValueError("name required")
```

### Scopes

Scopes are gathered from base classes that end with `Scope` and have an `apply(model)` method. Use `with_scopes(...)` or `without_scopes(...)` to toggle.

```python
# Disable all scopes for a query segment
User().without_scopes().where("id", 1).first()
```

### Table & model printing

Generate code stubs from your actual DB schema:

```python
print(User().print_model())     # model class with Field()s inferred
print(User().print_table())     # Table DSL from fields
```

### Migrations (simple runner)

```python
# Run all migrations in ./migrations in order
User.run_migrations(direction="up")
```

**Best practice**

- Always define `__table__`, `__driver__`, and `__database__` on your model.
- Prefer instance updates when you need events; prefer bulk updates for speed.
- Use `serialize(depth=0)` unless you intentionally include related data.

---

## CLI: `flask manage`

Framework1 ships a `flask manage` command that proxies to the package’s `manage.py`.

```bash
flask manage makemigrations
flask manage migrate
flask manage seed
```

> The command locates `manage.py` inside the installed `framework1` package and forwards arguments.

---

## Debugging

- **See generated SQL**
  - `QueryBuilder.dump()` / `dump_raw_sql()`
  - `ActiveRecord.raw_sql()` / `dump_sql()` / `dd_sql()` (terminates)
- **EXPLAIN**: `ActiveRecord.explain()` returns the DB’s query plan
- **Logger**: ORM debug logger prints with prefix `[orm.debug]`

---

## Security notes

- Ensure `APP_SECRET_KEY` is set; otherwise sessions and CSRF tokens are weak.
- Use `Request.csrf_token()` and `Request.validate_csrf()` on forms that mutate data.
- `render_template_string_safe_internal()` only reads templates from the package’s installed `templates/` folder, not arbitrary paths.
- Request sanitation: `Request.sanitize(key)` removes HTML tags; still validate and encode user input on output.

---

## Edge cases & pitfalls

**General**

- If a handler import fails, `discover_handlers(debug=True)` will print the exception. Keep `debug=True` during development.
- Navigation: `GetNavigation()` must return a **list** of items; each can include a `weight` used for sorting.

**Request**

- `datetime_()` returns **UTC** by default (`to_utc=True`). Pass `to_utc=False` to keep local tz.
- `grouped()` only groups keys with numeric indices, e.g., `filters[0][field]`.
- `to_list()` splits strings on commas; ensure your inputs don’t contain commas unless intended.

**Database**

- MySQL placeholders are `%s`; MSSQL adapter auto‑converts `%s` → `?` for you when using the adapter with `QueryBuilder`.
- MSSQL **pagination requires** an `ORDER BY`. `QueryBuilder.paginate()` enforces this.
- `QueryBuilder.update()` will raise if you forgot a `WHERE` clause (avoids full‑table updates).
- `insert_many()` requires all rows to have the **same keys**; otherwise it raises.
- `pquery()` expects your placeholder counts to match parameters. For MySQL, a single argument is replicated if needed; be explicit to avoid surprises.

**ActiveRecord**

- `delete()` returns:
  - affected row **count** for bulk deletes
  - the **instance** when deleting a loaded record (`.find(...).delete()`)
- Bulk `update()` with events enabled requires fetching rows first; prefer instance updates when events matter.
- `print_form()` and Field class mappings are best‑effort; review generated code before committing.

**Templating**

- `humanize_dt` expects ISO `"YYYY-mm-dd HH:MM:SS[.ffffff][tz]"`; unrecognized formats are returned as‑is.
- `is_active(query_fragment)` matches against the raw query string; ensure your nav URLs use consistent params.

---

## Appendix: Handy snippets

**Clean querystring pagination link**

```python
from framework1.core_services.Request import Request
req = Request()
prev_url = req.clean_url(req, key="page", value=2)
```

**Full‑text search (portable)**

```python
qb = (QueryBuilder().set_driver("mysql").table("articles")
      .where_full_text("title,body", "fraud", mode="boolean"))
```

**Case/when select**

```python
qb = (QueryBuilder().set_driver("mysql").table("payments")
      .select("id")
      .case([
        ("status='PENDING'", "Pending"),
        ("status='SETTLED'", "Settled")
      ], else_result="Other", alias="status_label"))
```

---

## Final notes

Framework1 is intentionally small and pragmatic. If you stick to the patterns above (container for cross‑cutting concerns, `Request` for inputs, QueryBuilder for SQL, ActiveRecord for domain logic), you’ll get a clean, testable codebase with predictable queries across MySQL and MSSQL.

