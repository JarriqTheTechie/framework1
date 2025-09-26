# Framework1 CLI

A small, pragmatic command‑line toolkit for bootstrapping **Framework1** apps: create project structure, scaffold resources (models, forms, tables, controllers & templates), generate database service classes, and run simple schema migrations.

This guide shows:

- Installation and setup expectations
- Command reference with realistic examples
- Best‑practice workflows for MySQL & MSSQL
- What each command writes to disk
- Common pitfalls & edge cases (with fixes)

> **Scope**: Everything documented here is based on the CLI entrypoint in `manage.py` and helpers in `database.py`, `form_related.py`, `generate_model.py`, `migrate.py`, `resource_handler.py`, and `structure.py`.

---

## Quick start

```bash
# 1) Initialize a new app layout under ./lib
python manage.py make:project --framework-path C:/path/to/framework1   # optional symlink for local development

# 2) Create a database service class (choose one)
python manage.py make:database Client mysql
# or
python manage.py make:database Client mssql

# 3) Scaffold a full resource (model + controller + templates + form + table + infolist)
python manage.py make:resource "Destruction Log" ClientDatabase \
  -f "name:CharField:max_length=150,nullable=false" \
     "logged_at:DateTimeField" \
     "notes:CharField:max_length=255,nullable=true"

# 4) (Alternative) Create just CRUD UI from an existing resource model
python manage.py make:crud destruction_logs

# 5) Generate DB tables based on discovered models
python manage.py migrate --dry-run  # inspect SQL
python manage.py migrate           # execute
```

---

## Installing & expected environment

- **Python** 3.10+
- **Framework1** installed/available on `PYTHONPATH` (the CLI imports `framework1.*`).
- **Flask** is expected at runtime for the generated controllers and templates.
- For **MySQL**: `mysql-connector-python` and reachable server credentials.
- For **MSSQL**: Microsoft ODBC Driver 17 (or compatible) and `pyodbc` configured.
- Run CLI from your project root (where `manage.py` lives). The CLI will write into `./lib/...`.

### Symlink to a local Framework1 checkout (optional)

If you are developing Framework1 locally, the CLI can create a project‑local link to it:

```bash
python manage.py make:project --framework-path C:/dev/framework1
```

On Windows, a junction (`mklink /j`) is used and may require an elevated shell.

---

## Directory layout produced by `make:project`

```
lib/
  globals/
  handlers/
    base.html           # copied from the Framework1 package
    users/              # copied when available in the Framework1 package
  services/
  storedprocs/
  utils/
  models/
  resources/
    css/
    js/
    images/
```

> **Tip**: `base.html` is copied from your installed Framework1 package. If your environment uses a virtual environment, the CLI reads it from `sys.prefix/Lib/site-packages/framework1/base.html`.

---

## Command reference

### `make:database` — create a database service class

```
python manage.py make:database <Name> (mysql|mssql)
```

Writes `lib/services/<Name>Database.py` with a ready‑to‑edit service class.

**MySQL template** highlights:

```python
class ClientDatabase(MySqlDatabase):
    env = "prod"
    connection_dict = dict(
        host="HOST NAME",
        port=3306,
        user="YOUR MYSQL DB USERNAME",
        password="YOUR PASSWORD",
        database="DATABASE NAME",
    )
```

**MSSQL template** highlights:

```python
class ClientDatabase(MSSQLDatabase):
    connection_string = 'DRIVER={ODBC Driver 17 for SQL Server};' \
                        'SERVER=SERVER NAME;' \
                        'PORT=1433;' \
                        'DATABASE=DATABASE NAME;' \
                        'Trusted_Connection=yes;' \
                        'Connection Timeout=10;'
```

**Best practices**

- Store secrets in environment variables or a secure config, not in Git.
- Use a named class per **business database** (e.g., `BillingDatabase`, `CRMDatabase`). Keep one responsibility per file.
- If your models will use MSSQL, set each model’s `__driver__ = "mssql"` (see notes under `make:resource` and `make:model`).

**Edge cases**

- Connection test failures won’t appear until you actually query. Validate credentials early using a quick `SELECT 1` through a tiny script.

---

### `make:project` — bootstrap `./lib` and optional Framework1 link

```
python manage.py make:project [--framework-path <path-to-framework1>]
```

Creates the standard `lib` tree, copies `base.html`, and (optionally) creates a symlink/junction named `framework1` to a local checkout.

**Edge cases**

- On Windows, `mklink /j` needs an Administrator shell.
- If `framework1/base.html` cannot be found in site‑packages, the copy step will fail. Ensure the Framework1 package is installed.

---

### `make:model` — generate a model class

```
python manage.py make:model <PascalName> [--fields name:Type[:k=v,...] ...] [--output lib/models]
```

Produces `lib/models/<PascalName>.py`.

- Default driver in the template is `"mysql"`. **Change to **`` if your service points at SQL Server.
- Default `__database__` is the string placeholder `"CHOOSE_YOUR_DATABASE_HERE"`; replace it with your service class name (e.g., `ClientDatabase`).

**Examples**

```bash
# Minimal (defaults to id/created_at/updated_at)
python manage.py make:model Invoice

# Explicit fields
python manage.py make:model Invoice \
  --fields "id:IntegerField:primary_key=true" \
           "number:CharField:max_length=30,unique=true" \
           "amount:DecimalField" \
           "issued_at:DateTimeField"
```

**What you get** (excerpt):

```python
class Invoice(ActiveRecord):
    __table__ = "invoices"
    __driver__ = "mysql"               # change to "mssql" if needed
    __database__ = "CHOOSE_YOUR_DATABASE_HERE"
    __primary_key__ = "id"

    id = IntegerField(primary_key=True)
    number = CharField(max_length=30, unique=True)
    amount = DecimalField()
    issued_at = DateTimeField()
```

**Edge cases**

- `--fields` parser treats bare numbers as integers and `true/false` (case‑insensitive) as booleans. Strings with spaces should be quoted.
- The generator **does not** infer driver from your database service. Set `__driver__` yourself.

---

### `make:resource` — scaffold a full resource

```
python manage.py make:resource <Resource Name[,Another]> <DatabaseServiceName> \
  [-f|--fields name:Type[:k=v,...] ...]
```

Creates:

```
lib/handlers/<snake_plural>/
  <Pascal>.py            # model
  <Pascal>Controller.py  # Flask controller with routes
  forms/<Pascal>Form.py
  tables/<Pascal>Table.py
  infolists/<Pascal>InfoList.py
  templates/
    index.html  create.html  edit.html  details.html
```

**Name transformation**

- `"Destruction Log"` → `DestructionLog` (class), `destruction_logs` (folder & table), `destruction-logs` (slug), human titles derived automatically.
- You can pass multiple resources separated by commas; each uses the **same** `<DatabaseServiceName>`.

**Field syntax** (applies to the *model* created under the resource):

```
"name:CharField:max_length=150,nullable=false"
"amount:DecimalField:default=0"
"starts_at:DateTimeField"
```

**Driver note**

- The scaffolded model sets `__driver__ = "mysql"` by default. If you are on SQL Server, **change to** `"mssql"` in the generated model.

**Generated Controller**

- Uses `@injectable_route` to provide routes like `/destruction-logs`, `/destruction-logs/create`, `/destruction-logs/<id>`, etc.
- Integrates the generated `Form` and `Table` classes.

**Best practices**

- Keep `<DatabaseServiceName>` aligned with a single database. Cross‑DB joins are not supported here.
- Start with minimal fields (id, timestamps) and evolve using `migrate` (see below).
- Prefer single‑word field names in **snake\_case** to match the DSL defaults.

**Edge cases**

- If the destination resource folder already exists, files are overwritten silently. Use version control.
- Irregular plurals are handled by `inflect`, but some words (e.g., “staff”) may pluralize unexpectedly. Rename the folder/class if you prefer a custom plural.

---

### `make:form`, `make:table`, `make:crud` — generate UI from a resource model

```
python manage.py make:form  <resource_folder_name>
python manage.py make:table <resource_folder_name>
python manage.py make:crud  <resource_folder_name>   # runs form + table
```

- These commands **read the model** under `lib/handlers/<resource>/models/*.py` and emit UI classes.
- The generator searches for `class <Name>(ActiveRecord):` and extracts field declarations like `xyz = CharField(...)`.
- `make:table` also creates a matching **InfoList**.

**Expectations**

- Your resource directory must exist and contain a single model file; otherwise you’ll see messages like:
  - `❌ Resource '<name>' does not exist or structure is invalid.`
  - `❌ No model found in .../models`
  - `❌ No ActiveRecord class found in ...`

**Best practices**

- Hand‑tune labels, CSS classes, and grouping after generation—the DSL stubs are intentionally conservative.
- Re‑run `make:form` after adding or renaming model fields to keep the UI in sync.

---

### `migrate` — discover models and apply schema changes

```
python manage.py migrate [--dry-run] [--replay]
```

- Scans for models under `lib/` and loads their **last known schema** from history.
- For a brand‑new model (or with `--replay`) it emits a **CREATE TABLE** statement.
- For existing models, it diffs current fields against history and runs targeted `ALTER TABLE` statements to add/modify/drop columns.
- `--dry-run` prints SQL without executing.

**Best practices**

- Always run with `--dry-run` in CI to catch dangerous diffs.
- Review generated SQL whenever you rename fields (diff shows a drop+add rather than a rename).
- Keep model field declarations the single source of truth.

**Edge cases**

- If a model sets `__ignore_migration__ = True`, it will be skipped.
- The generator relies on Framework1’s migrations helpers; ensure those are installed.
- `--replay` recreates the table definition from the current model. If the target table already exists and the SQL does not use `IF NOT EXISTS`, the database may error—use `--dry-run` first.

---

## Field definition grammar (used by `--fields`)

```
name:Type[:arg=value[,arg=value...]]
```

- `Type` is one of your Field classes (e.g., `IntegerField`, `CharField`, `DateTimeField`, `DecimalField`, `BooleanField`, `JsonField`).
- Supported value coercions in the parser:
  - `true` / `false` → Python booleans
  - `123` → integer
  - non‑numeric strings must be quoted in your shell if they contain spaces

**Examples**

```
"title:CharField:max_length=200,nullable=false,unique=true"
"score:DecimalField:default=0"
"published_at:DateTimeField"
```

---

## Naming, tables, and slugs

Given a raw name, the CLI derives multiple variants (using `inflect` and `slugify`):

| Input               | Class (`Pascal`) | Folder/Table (`snake_plural`) | Slug (`slug_plural`) |
| ------------------- | ---------------- | ----------------------------- | -------------------- |
| `"Destruction Log"` | `DestructionLog` | `destruction_logs`            | `destruction-logs`   |
| `"Invoice"`         | `Invoice`        | `invoices`                    | `invoices`           |

You can always rename artifacts after generation; the controller, templates, and UI classes reference each other consistently within the same folder.

---

## MSSQL vs MySQL considerations

- **Placeholders**: The database adapters handle `%s` vs `?` internally; generated SQL from models and query builder will be bound correctly.
- **Driver flag**: Set `__driver__` on each model (`"mysql"` or `"mssql"`) so pagination and quoting rules are correct.
- **ODBC setup (MSSQL)**: Ensure the declared driver name in the connection string matches what is installed (e.g., `{ODBC Driver 17 for SQL Server}`).

---

## Troubleshooting & common pitfalls

### Generated model still points to MySQL

If you scaffolded on SQL Server, edit the model:

```python
__driver__ = "mssql"
__database__ = ClientDatabase   # your MSSQL service class
```

### `make:form` says the resource is invalid

Ensure you ran `make:resource <Name> <DatabaseServiceName>` first. The generator expects:

```
lib/handlers/<resource>/models/<Pascal>.py
lib/handlers/<resource>/forms/
```

### Windows symlink creation fails

Run the shell **as Administrator** or create the junction yourself, then rerun without `--framework-path`.

### Pluralization looks wrong

Some words have tricky plurals. Rename the folder and class manually after generation.

### Migrations won’t pick up your model

- The migrator discovers under `lib/` only. Ensure your model lives there.
- If you added `__ignore_migration__ = True` intentionally, remove it first.

---

## Suggested workflow (best practice)

1. **Create the project skeleton** once: `make:project` (+ symlink if you hack on Framework1).
2. **Create a database service** per database you’ll connect to with `make:database`.
3. **Scaffold resources** with minimal fields using `make:resource` so you get the model + UI + controller glue.
4. **Iterate on the model** fields directly in code.
5. **Regenerate forms/tables** with `make:form` / `make:table` when fields change.
6. **Migrate**: run `migrate --dry-run`, review, then `migrate`.
7. **Hand‑finish UI**: tweak labels, classes, grouping in the generated form/table; add controller logic as needed.

---

## Safety notes

- Generators **overwrite** files. Commit before running, and use a dedicated branch for large scaffolds.
- Migrations run **DDL statements** against your database. Always dry‑run and use non‑production connections during development.

---

## Reference: Commands & options (at a glance)

| Command         | Purpose                                                                       | Key options             |          |
| --------------- | ----------------------------------------------------------------------------- | ----------------------- | -------- |
| `make:project`  | Create `lib/` layout, copy `base.html`, optionally symlink a local Framework1 | `--framework-path`      |          |
| `make:database` | Generate a DB service class                                                   | \`(mysql                | mssql)\` |
| `make:model`    | Generate a single model file                                                  | `--fields`, `--output`  |          |
| `make:resource` | Scaffold full resource (model, controller, templates, form, table, infolist)  | `-f/--fields`           |          |
| `make:form`     | Generate a form class from an existing resource model                         | —                       |          |
| `make:table`    | Generate a table class from an existing resource model                        | —                       |          |
| `make:crud`     | Generate form + table                                                         | —                       |          |
| `migrate`       | Diff model schema vs history and apply SQL                                    | `--dry-run`, `--replay` |          |

---

## Appendix: Field examples you can copy‑paste

```
"id:IntegerField:primary_key=true"
"email:CharField:max_length=190,unique=true,nullable=false"
"status:CharField:max_length=20,default='draft'"
"amount:DecimalField"
"is_active:BooleanField:default=true"
"meta:JsonField:nullable=true"
"created_at:DateTimeField:default=CURRENT_TIMESTAMP"
"updated_at:DateTimeField:default=CURRENT_TIMESTAMP"
```

---

**That’s it!** The CLI is intentionally lean—generate, review, then customize. If you hit a rough edge that isn’t covered here, keep the symptoms and command you ran, then adjust the generated files or rerun with corrected inputs.

