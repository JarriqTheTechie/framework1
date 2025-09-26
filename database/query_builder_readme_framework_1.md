# QueryBuilder — Framework1

A fluent, database-agnostic SQL builder for Python with first‑class support for MySQL and SQL Server (MSSQL). It outputs parameterized SQL and a flat list of parameters, so you can pass the result directly into your database adapter.

> Works standalone or as the query core for `ActiveRecord`. This guide focuses on `QueryBuilder` itself.

---

## Table of Contents
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Selecting Data](#selecting-data)
- [Filtering (WHERE)](#filtering-where)
- [Grouping & Aggregates](#grouping--aggregates)
- [Joins](#joins)
- [Ordering & Pagination](#ordering--pagination)
- [Unions & CTEs](#unions--ctes)
- [Subqueries & Nesting](#subqueries--nesting)
- [Full‑Text Search & LIKE](#fulltext-search--like)
- [Mutation Helpers](#mutation-helpers-insert-update-delete-upsert)
- [Raw SQL & Debugging](#raw-sql--debugging)
- [Driver Notes (MySQL vs MSSQL)](#driver-notes-mysql-vs-mssql)
- [Edge Cases & Best Practices](#edge-cases--best-practices)
- [API Cheatsheet](#api-cheatsheet)

---

## Key Features
- Fluent builder that always returns **(sql, params)** via `.get()`
- Safe parameter binding (no string interpolation required)
- MySQL & MSSQL aware: quoting, pagination, full‑text, random ordering
- Rich WHERE helpers: `between`, `in/not_in`, `null/not_null`, date/time helpers, nested predicates
- Aggregates: `group_by`, `having`
- Joins: inner/left/right/full/cross + raw join conditions
- Subqueries in select/where/join and nesting blocks
- Pagination with driver‑specific strategies
- DDL‑free insert/update/delete helpers (generate SQL + params)
- Utilities: `with_cte`, `union/all`, `distinct`, `case`, `lateral_join`

---

## Quick Start

```python
from framework1.database.QueryBuilder import QueryBuilder
from framework1.core_services.MySqlDatabase import MySqlDatabase  # or MSSQLDatabase

# Build a query
qb = (QueryBuilder()
      .set_driver("mysql")              # or "mssql"
      .table("users", alias="u")
      .select("u.id", ("u.name", "full_name"), "u.email")
      .where("u.active", "=", 1)
      .where_like("u.email", "%@example.com")
      .order_by("u.id", "DESC")
      .limit(10).offset(0))

sql, params = qb.get()
# sql -> SELECT u.id, u.name AS full_name, u.email FROM users AS u ...
# params -> [1, "%@example.com", 10, 0]

# Execute via adapter
rows = MySqlDatabase().query(sql, params)
```

### Using the builder object directly in adapters
Adapters accept a `QueryBuilder` instance and call `.get()` internally:

```python
rows = MySqlDatabase().query(
    QueryBuilder().set_driver("mysql").table("payments").where("status", "=", "OK").limit(5)
)
```

---

## Core Concepts
- **Driver**: Call `set_driver("mysql"|"mssql")` early. It controls quoting, pagination, and certain functions.
- **Table & Alias**: `table("invoices", alias="i")`.
- **Select List**: `select("id", ("email", "user_email"))`. Use tuples for aliases; `select_raw("COUNT(*)")` for raw projections.
- **Params**: Values go into `.parameters` in the order you add conditions. Placeholders are `%s` (adapters translate to `?` for MSSQL).
- **`Raw`**: Escape hatch to inject driver SQL fragments: `where(Raw("UPPER(name)"), "=", Raw("'JOE'"))`.

---

## Selecting Data
```python
# Basic
qb.select("id", "name").table("users")

# Add at any time
qb.add_select("email", (Raw("COUNT(*)"), "cnt"))

# Subquery in SELECT
sub = (QueryBuilder().set_driver("mysql").table("orders")
       .select_raw("COUNT(*)").where("user_id", "=", Raw("u.id")))
qb.table("users", "u").add_select_subquery(sub, alias="order_count")
```

---

## Filtering (WHERE)

### Equality, comparisons, dictionaries
```python
qb.where("age", ">", 18).where({"active": 1, "tenant_id": "MSFT"})
```

### NULL checks
```python
qb.where_null("deleted_at")
qb.where_not_null("verified_at")
```

### IN / NOT IN
```python
qb.where_in("id", [1,2,3])
qb.where_not_in("status", ["archived", "void"])
```

### BETWEEN (numbers or dates)
```python
qb.where_between("amount", 100, 500)
qb.where_between_dates("created_at", date(2025,1,1), date(2025,12,31))
```

### LIKE (case‑sensitive options)
```python
qb.where_like("email", "%@domain.com")
qb.where_not_like("name", "Test%")
# Case‑sensitive: uses MSSQL collation if available
qb.where_like("name", "joe%", case_sensitive=True)
```

### Column‑to‑column comparisons
```python
qb.where_column("updated_at", ">=", "created_at")
```

### Nesting (grouped predicates)
```python
qb.nest(lambda q: (
    q.where("status", "=", "OPEN").or_where("status", "=", "NEW")
)).where("tenant_id", "=", "MSFT")

# OR‑group
qb.or_nest(lambda q: q.where("country", "=", "BS").where("vip", "=", 1))
```

### Convenience across columns
```python
qb.where_any_columns(["first_name", "last_name"], "LIKE", "%jo%")  # OR across the set
qb.where_all_columns(["is_active", "email_verified"], "=", 1)        # AND across the set
qb.where_none(["deleted_at", "archived_at"])                           # both NULL
```

### EXISTS / NOT EXISTS
```python
exists_q = (QueryBuilder().set_driver("mysql").table("orders")
            .select_raw("1").where("orders.user_id", "=", Raw("u.id")))
qb.table("users", "u").where_exists(exists_q)
```

---

## Grouping & Aggregates
```python
qb.group_by("tenant_id", "status")
qb.having("COUNT(*)", ">", 10)         # or qb.having_raw("SUM(amount) > 1000")
```

---

## Joins
```python
(qb.table("orders", "o")
   .left_join("users u", "o.user_id", "=", "u.id")
   .join("tenants t", "u.tenant_id", "=", "t.id")
   .join_raw("currencies c", "c.code = o.ccy AND c.active = 1"))
```
- Types: `join` (INNER), `left_join`, `right_join`, `full_join` (MSSQL), `cross_join`.
- For complex ON clauses, use `join_raw`.

### Lateral joins (escape hatch)
```python
sub = (QueryBuilder().set_driver("mysql").table("payments")
       .select_raw("SUM(amount) AS total").where("payments.user_id", "=", Raw("u.id")))
qb.table("users", "u").lateral_join(sub, alias="p", on_clause="1=1")
```

---

## Ordering & Pagination
```python
qb.order_by("created_at", "DESC").order_by_raw("RAND()")      # MySQL random
qb.in_random_order()                                            # NEWID() on MSSQL, RAND() otherwise

# Pagination
qb.order_by("id", "ASC").paginate(page=2, per_page=25)       # adds LIMIT/OFFSET (MySQL) or OFFSET/FETCH (MSSQL)
```
**Notes**
- MSSQL **requires ORDER BY** for OFFSET/FETCH; `.paginate()` enforces it.
- `.remove_limit()` clears LIMIT/OFFSET/FETCH — handy before reuse.

---

## Unions & CTEs
```python
q1 = QueryBuilder().set_driver("mysql").table("a").select("id").where("active",1)
q2 = QueryBuilder().set_driver("mysql").table("b").select("id").where("active",1)
unioned = q1.union_all(q2)   # or .union(q2)

# CTEs
base = QueryBuilder().set_driver("mysql").table("orders").select("user_id", (Raw("SUM(amount)"), "total")) \
       .group_by("user_id")
qb = (QueryBuilder().set_driver("mysql")
      .with_cte("totals", base)
      .table("totals").select("user_id", "total").where("total", ">", 1000))
```

---

## Subqueries & Nesting
- **In SELECT**: `add_select_subquery(sub, alias)`
- **In WHERE**: pass a `QueryBuilder` as the third arg: `where("id", "IN", sub)`
- **Standalone nested predicates**: `nest` / `or_nest` build `(...)` groups without subselects.

---

## Full‑Text Search & LIKE
```python
# MySQL: MATCH AGAINST (supports NATURAL LANGUAGE, BOOLEAN)
qb.set_driver("mysql").where_full_text("title", "bahamas banking", mode="BOOLEAN")

# MSSQL: CONTAINS(column, @query)
qb.set_driver("mssql").where_full_text("title", "\"risk\" NEAR bank")
```
> `or_where_full_text` variants are also available.

---

## Mutation Helpers (INSERT / UPDATE / DELETE / UPSERT)
These generate SQL and params; you still execute them via your adapter.

### INSERT
```python
sql, params = (QueryBuilder().set_driver("mysql").table("users")
               .insert({"email": "a@b.com", "active": 1}))
```

### INSERT MANY
```python
rows = [
  {"email": "a@b.com", "active": 1},
  {"email": "c@d.com", "active": 0},
]
sql, params = QueryBuilder().set_driver("mysql").table("users").insert_many(rows)
```

### INSERT OR IGNORE (driver‑aware)
```python
# MySQL: INSERT IGNORE ...
# MSSQL: emits IF NOT EXISTS (...) INSERT ... per row
sql, params = (QueryBuilder().set_driver("mssql").table("tags")
               .insert_or_ignore([{ "name": "aml" }, { "name": "kyc" }]))
```

### INSERT USING (INSERT … SELECT)
```python
sub = (QueryBuilder().set_driver("mysql").table("staging_users").select("email", "active"))
sql, params = (QueryBuilder().set_driver("mysql").table("users")
               .insert_using(["email","active"], sub))
```

### UPDATE (safe by default)
```python
qb = (QueryBuilder().set_driver("mysql").table("users")
      .where("id", "=", 7))
sql, params = qb.update({"active": 0})     # raises if WHERE is missing
```

### UPSERT
```python
sql, params = (QueryBuilder().set_driver("mysql").table("users")
               .upsert([
                 {"email": "a@b.com", "active": 1},
                 {"email": "c@d.com", "active": 0}
               ], unique_by=["email"], update_columns=["active"]))
```

### UPDATE OR INSERT (single row)
```python
sql, params = (QueryBuilder().set_driver("mssql").table("rates")
               .update_or_insert({"ccy": "USD", "date": "2025-08-01"}, {"rate": 1.25}))
```

### Counters
```python
QueryBuilder().set_driver("mysql").table("stats").where("id","=",1).increment("views", 3)
QueryBuilder().set_driver("mysql").table("stats").where("id","=",1).decrement_each({"a":2,"b":5})
```

### DELETE
```python
sql, params = QueryBuilder().set_driver("mysql").table("logs").where("days_old", ">", 30).delete()
```

> All helpers return SQL+params; execute with your adapter and commit where appropriate.

---

## Raw SQL & Debugging
```python
qb.dump()          # prints SQL + params, keeps chaining
qb.dump_raw_sql()  # prints SQL with params substituted (for dev only)
qb.dd()            # prints & raises DebugBreak (stops flow)
qb.dd_raw_sql()    # prints substituted SQL & raises

qb.raw_sql()       # (when used via ActiveRecord/Ext) returns substituted SQL string
qb.explain()       # run EXPLAIN <query> via adapter (driver‑specific)
qb.tap(lambda q: print(q.get()))  # observe and continue
qb.debug()         # logs substituted SQL to orm.debug logger (when mixed in via Ext)
```

---

## Driver Notes (MySQL vs MSSQL)
- **Placeholders**: Builder uses `%s`. The MSSQL adapter automatically converts to `?` for `pyodbc`.
- **Quoting**: `_quote_column()` uses backticks for MySQL, square brackets for MSSQL.
- **Pagination**: MySQL uses `LIMIT %s OFFSET %s`; MSSQL uses `ORDER BY ... OFFSET %s ROWS FETCH NEXT %s ROWS ONLY`.
- **Random order**: `RAND()` (MySQL) vs `NEWID()` (MSSQL). Use `.in_random_order()`.
- **Full‑text**: `MATCH ... AGAINST` (MySQL) vs `CONTAINS(column, @query)` (MSSQL).

---

## Edge Cases & Best Practices

### Safety & correctness
- **Always set the driver** early: `.set_driver("mysql"|"mssql")`.
- **Require WHERE on update**: `.update()` raises if no WHERE (prevents accidental full‑table updates).
- **Parameter ordering**: When composing with subqueries/unions, params are appended in the order you add parts. Execute exactly the returned `params` list.
- **Clearing pagination**: Reusing a builder? Call `.remove_limit()` to clear limit/offset/fetch (the builder also scrubs old pagination ints in `.paginate()`).
- **MSSQL pagination**: add `order_by` **before** calling `.paginate()` or you’ll get a `ValueError`.
- **Case‑sensitive LIKE**: Collation hint is MSSQL‑specific; on MySQL ensure a case‑sensitive collation on the column or use a BINARY prefix.

### Performance
- Prefer `where_in(..., values)` over OR‑chains for large sets (but for *very* large lists, consider staging tables/CTEs).
- Push aggregates to the DB (`group_by` + `having`) and paginate at the DB layer.
- Use `select()` to limit columns—avoid `*` in high‑volume paths.

### Readability & reuse
- Use `nest()` to clearly group boolean logic; it prevents precedence mistakes.
- `clone()` a builder before applying counting/pagination mutations when you need both total count and row data.
- Use `add_select_subquery()` or `with_cte()` to express complex projections without leaving the builder.

### Not covered / limitations
- No automatic escaping for `Raw` fragments—ensure they are trusted and driver‑valid.
- `lateral_join` emits a generic LEFT JOIN LATERAL‑style string; some engines may not support it—treat as an advanced escape hatch.
- `insert_or_ignore` for MSSQL expands per‑row `IF NOT EXISTS` checks; for very large batches, prefer MERGE‑based `upsert`.

---

## API Cheatsheet

### Setup & Introspection
- `set_driver(driver)` → `"mysql"|"mssql"`
- `table(name, alias=None)`
- `select(*cols)`, `add_select(*cols)`, `select_raw(sql)`
- `add_select_subquery(sub_qb, alias)`
- `get()` → `(sql, params)`, `to_sql(include_select=True)`
- `get_parameters()`
- `clone()`

### WHERE
- `where(col, op="=", val)`, `or_where(...)`
- `where_in(col, values)`, `or_where_in`, `where_not_in`, `or_where_not_in`
- `where_between(col, start, end)`, `or_where_between`
- `where_null(col)`, `where_not_null(col)` (+ `or_` variants)
- `where_like(col, pattern, case_sensitive=False)` (+ not_like, or_ variants)
- `where_date/month/day/year/time/today/past/future/before_today/after_today`
- `where_column(col1, op, col2)`, `or_where_column`
- `where_any_columns(cols, op, val)`, `where_all_columns`, `where_none(cols)`
- `where_exists(sub)`, `where_not_exists(sub)`
- `nest(fn)`, `or_nest(fn)`

### GROUP/HAVING
- `group_by(*cols)`, `group_by_raw(sql)`
- `having(col, op, val)`, `or_having`, `having_raw`, `or_having_raw`

### JOINS
- `join(table, c1, op, c2, join_type="INNER")`
- `left_join`, `right_join`, `full_join`, `cross_join`, `join_raw`
- `lateral_join(sub, alias, on_clause)`

### ORDER/PAGINATION
- `order_by(col, dir="ASC")`, `order_by_raw(sql)`, `latest(col)`, `oldest(col)`, `in_random_order()`
- `limit(n)`, `offset(n)`, `remove_limit()`, `paginate(page, per_page=10)`

### SET Ops & CTE
- `distinct()`
- `union(sub)`, `union_all(sub)`
- `with_cte(name, query)`

### Mutations
- `insert(data)`, `insert_many(rows)`
- `insert_get_id(data)` (MySQL/MSSQL only)
- `insert_or_ignore(rows)` (driver‑aware)
- `insert_using(columns, subquery)`
- `update(values)` (requires WHERE)
- `upsert(rows, unique_by, update_columns)`
- `update_or_insert(match, updates)`
- `delete()`
- `increment(col, amount=1)`, `decrement(col, amount=1)`, `increment_each(map)`, `decrement_each(map)`

### Utilities & Debug
- `case(cases, else_result, alias)`
- `substitute_params(sql, params)`
- `dump()`, `dd()`, `dump_raw_sql()`, `dd_raw_sql()`
- (when mixed via Ext): `raw_sql()`, `explain()`, `tap(cb)`, `debug()`

---

## End‑to‑End Example (MSSQL)

```python
from framework1.database.QueryBuilder import QueryBuilder
from framework1.core_services.MSSQLDatabase import MSSQLDatabase

qb = (QueryBuilder()
      .set_driver("mssql")
      .table("payments", alias="p")
      .select("p.id", "p.amount", (Raw("FORMAT(p.created_at, 'yyyy-MM-dd')"), "created"))
      .left_join("tenants t", "p.tenant_id", "=", "t.id")
      .where("t.code", "=", "MSFT")
      .where_between("p.amount", 500, 50000)
      .where_null("p.deleted_at")
      .order_by("p.id", "ASC")
      .paginate(page=1, per_page=25))

sql, params = qb.get()
rows = MSSQLDatabase().query(sql, params)  # adapter converts %s -> ? automatically
```

---

## FAQ
**Q: Why am I getting a ValueError on `.update()`?**  
A: The builder refuses to emit an UPDATE without a WHERE. Add a predicate.

**Q: Why does my MSSQL pagination complain?**  
A: Add at least one `order_by` before calling `.paginate()`.

**Q: Can I re‑use the same builder for multiple queries?**  
A: Yes, but call `.remove_limit()` or `clone()` to avoid stale LIMIT/OFFSET/params.

**Q: Why `%s` placeholders on MSSQL?**  
A: The MSSQL adapter replaces `%s` with `?` for `pyodbc` before execution.

---

Happy querying! ✨

