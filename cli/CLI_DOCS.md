# Framework1 CLI Playbook

All commands run via `flask manage <command>`.

## make:project
- Scaffolds `lib/` folders, base templates, and `.env` from the installed package.
- Copies `users`, `ADAuth`, `DESBus`, `DomainEvent*`, `ViewState`, `InformationSchema` when available.
- Args: `--framework-path` to symlink a framework folder (overwrite is not supported; delete first if needed).

```bash
flask manage make:project
flask manage make:project --framework-path ../framework1-src
```

## make:database
- Generates `lib/services/{name}Database.py` for `mysql` or `mssql`.
- Validates identifiers; handles legacy/current import layouts.

```bash
flask manage make:database App mysql
flask manage make:database Reporting mssql
```

## make:resource
- Builds controller, model, form, table, infolist, templates.
- Includes `_ensure_permission` hook and CSRF protection on create/update.
- Fields format: `name:FieldType:key=val,...`

```bash
flask manage make:resource invoice AppDatabase \
  -f customer_id:IntegerField amount:DecimalField:precision=12,scale=2 \
  status:CharField:max_length=32,default=pending

flask manage make:resource user AppDatabase \
  -f name:CharField email:CharField:max_length=190
```

## make:form / make:table / make:crud
- `make:form <resource>` generates a form from the resource model.
- `make:table <resource>` generates table + infolist.
- `make:crud <resource>` runs both.

```bash
flask manage make:form invoice
flask manage make:table invoice
flask manage make:crud invoice
```

## make:model
- Creates `lib/models/{Name}.py` with ActiveRecord fields and `create_table()`.
- Fields: list of dicts (name/type/nullable/default/primary_key).

```bash
flask manage make:model Invoice \
  --fields id:IntegerField:primary_key=true \
  customer_id:IntegerField amount:DecimalField:precision=12,scale=2
```

## migrate
- Diffs model schema history and issues ALTER/CREATE.
- `--replay` recreates tables from current snapshot.
- `--dry-run` prints SQL without executing.

```bash
flask manage migrate --dry-run
flask manage migrate --replay
```

---

Tips:
- Identifiers must be valid Python identifiers (letters/numbers/underscore, not starting with a digit).
- Generators skip existing files unless an overwrite flag exists; review generated SQL before applying in production.
