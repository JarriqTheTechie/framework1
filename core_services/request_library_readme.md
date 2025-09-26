# Request Library (Flask) — Comprehensive Guide

**Scope:** This guide documents the `Request` helper found in `framework1.core_services.Request` (a thin wrapper around `flask.request`). It explains best‑practice usage patterns, gotchas, and edge cases. **Only **``** is covered here.**

---

## Quick Start

```python
from framework1.core_services.Request import Request

req = Request()  # use inside a Flask view function

name = req.input("name")
age = req.integer("age", default=0)
active = req.boolean("active", default=False)

# Date/time helpers (auto-parse common formats)
born = req.date("dob")                       # -> datetime.date or None
appt = req.datetime_("appt", tz="America/Nassau")  # -> UTC datetime by default
when = req.time("remind_at")                 # -> datetime.time or None

# Files
avatar = req.file("avatar")
if avatar and req.is_image("avatar"):
    saved_path = avatar.save(prefix="user_", suffix="avatar", suffix_separator="_")

# Validation (see “Validation” section)
errors = req.validate({
    "email": ["required", "email"],
    "age": ["integer", lambda f,v,all: "must be >=18" if v and int(v) < 18 else None],
})
if errors:
    return {"errors": errors}, 422

# Dataclass binding (see “Binding to dataclasses”)
from dataclasses import dataclass
@dataclass
class Signup:
    name: str
    age: int = 0
    tags: list[str] = None

payload = req.bind_to(Signup, defaults={"tags": []})  # type-coerces if possible
```

> **Recommendation:** Call `Request()` *inside* your Flask view so it reflects the current request context. Avoid storing it globally.

---

## Where values are read from

`Request.input(key, default=None, cast: type|"date"|"datetime"|"time"=None)` returns the first match in this order:

1. Query-string list form: if key contains `[]`, from `request.args.getlist(key)`
2. Path params: `request.view_args`
3. Query-string: `request.args`
4. POST form body: `request.form`
5. JSON body (only if `Content-Type: application/json`): `request.json`

If nothing is found, `default` is returned.

### Casting behavior

- **bool**: truthy strings `"true","1","yes","on"` → `True`; lists get element-wise conversion
- **"date" | "datetime" | "time"**: delegates to `date()`, `datetime_()`, `time()`
- Any other type (e.g., `int`, `float`, `str`, custom class): best-effort cast; failures return `default`

**Helpers**

- `query(key, default=None)`: get from query string (supports `[]` → list)
- `string()`, `integer()`, `float()`
- `to_list(key, default=None, cast=str)`: comma-split strings, list cast
- `lists()`: returns only keys ending with `[]` as dict of lists

---

## Grouping dynamic inputs

### `form(group: str)` — simple one-level grouping

For inputs like `billing[address]` and `billing[city]`:

```html
<input name="billing[address]" value="123 Main" />
<input name="billing[city]" value="Nassau" />
```

```python
req.form("billing")
# {"address": "123 Main", "city": "Nassau"}
```

### `grouped(prefix: str=None, sort=True, as_list=True)` — indexed groups

Handles arrays of structs like `filters[0][field]`, `filters[0][operator]`, `filters[1][field]`:

```python
req.grouped("filters")
# [
#   {"field": "amount", "operator": ">", "value": "5000"},
#   {"field": "status", "operator": "=", "value": "Open"}
# ]
```

**Notes**

- Index (`filters[0]`) **must be numeric**.
- Keys must have at least two bracket levels: `name[index][field]`.
- If `prefix` is omitted, it attempts auto-detection on any `name[index][field]` pattern.
- `as_list=False` returns `{index: {...}}` mapping.

---

## Dates, times & timezones

### Parsing

- `date(key)` tries common formats: `YYYY-MM-DD`, `DD-MM-YYYY`, `MM/DD/YYYY`, `DD/MM/YYYY`.
- `datetime_(key, tz="UTC", to_utc=True)` tries multiple datetime formats, assumes the provided `tz` for naive parses, and converts to **UTC** by default.
- `time(key)` accepts `HH:MM[:SS]` and `h:MM AM/PM`.

### Relative helpers (all accept `tz` where applicable)

- `now(tz)`, `today(tz)`, `tomorrow(tz)`, `yesterday(tz)`
- `days_ago(n, tz)`, `days_in_future(n, tz)`, `weeks_ago(n, tz)`
- `start_of_week(tz, week_start=0)`, `start_of_month(tz)`, `end_of_month(tz)`, `months_ago(n, tz)`

**Best practices**

- Use `datetime_(..., tz=<user_tz>, to_utc=True)` to normalize to UTC at the edge.
- Always store timestamps in UTC; render in the user’s timezone on output.
- Validate ambiguous formats (e.g., `01/02/2025`) via explicit `tz` and format guidance in your UI.

---

## Presence & conditional utilities

- `has(key)`, `has_any([k1,k2])`, `has_all([...])`, `has_only([...])`
- `filled(key)` → value is not `None` and not empty string
- `is_not_filled(key|list)`; `any_filled(list)`
- `when_has(key, callback, default=None)` and `when_filled(key, callback, default=None)`
- `missing(key)`, `when_missing(key, callback, default=None)`

**Pattern**: build flexible filters

```python
def apply_amount(q, val):
    return q.where("amount", ">=", float(val))

amount = req.input("min_amount")
query = base_query
query = req.when_filled("min_amount", lambda v: apply_amount(query, v), default=query)
```

---

## Request metadata & content negotiation

- `path()`, `url()`, `host()`, `ip()`, `ips()`
- `method` property and `is_method("POST")`
- `headers(key=None, default=None)` → single header or all
- `get_acceptable_content_types()` parses `Accept` header
- `accepts(content_type|[...])` and `expects_json()`
- `get_locale()` from `Accept-Language` (e.g., `"en-US" → "en-US"`)

**Best practices**

- Use `expects_json()` to branch API vs. HTML responses in mixed routes.
- Don’t trust `ip()` behind proxies; rely on your proxy’s forwarded header policy.

---

## Files & uploads

### Reading files

- `file(key, default=None, multiple=False)` → `UploadedFile` or list thereof
- `has_file(key)`; `is_image(key)`

### `UploadedFile` API

- `.save(path=None, prefix="", suffix="", prefix_separator="", suffix_separator="", keep_name=False, upload_dir=os.getenv("UPLOAD_DIR") or "uploads")` → returns saved path
- `.extension()`; `.path()` (original filename); `.mimetype()`
- `.size(format='kb'|'mb'|'gb'|bytes)`
- `.filename` property

**Best practices**

- Always validate extension and MIME type (whitelist) before saving.
- Store uploads **outside** your static web root; serve via signed URLs or authenticated endpoints.
- Generate unique names: use `prefix`/`suffix` or the default UUID to avoid collisions.
- Consider virus scanning and size limits at the web server/wsgi layer.

**Edge case**

- `size()` reads from the stream; depending on the WSGI server, this can advance the file pointer. If you call `size()` before `save()`, you may want to re-seek the stream (`file.file.stream.seek(0)`) prior to saving to ensure the full content is written.

---

## Cookies, session & flash

- `session()` returns `flask.session`
- `cookie(key, default=None)`, `has_cookie(key)`
- `flash()`, `flash_only(keys)`, `flash_except(keys)` → store “old input”
- `old(key, default=None)` → retrieve flashed value

**Form pattern**

```python
if req.is_method("POST"):
    errors = ...
    if errors:
        req.flash()
        return redirect("/signup")

# later, on GET
old_name = req.old("name", "")
```

---

## CSRF utilities

- `csrf_token(key="csrf_token")` → stores random token in `session[key]` and returns it
- `validate_csrf(token, key="csrf_token")` → constant‑time compare vs stored token

**Best practices**

- Render a hidden input with `csrf_token()` on every POST form.
- Rotate tokens per form/session as your threat model requires.

---

## Sanitization

- `sanitize(key)` → strips HTML tags and trims

Use this for free‑text fields if you render unescaped output anywhere (but prefer escaping by default and HTML‑encode on output).

---

## Validation

`validate(schema: dict[str, list]) -> dict[str, list[str]]`

- `schema` maps field → list of rules. Each rule is either a string (resolved via `validators.get_rule`) or a callable.
- If a rule returns a non‑empty string, it is recorded as an error message.

**Example**

```python
errors = req.validate({
  "email": ["required", "email"],
  "age": ["integer", lambda f,v,all: ">= 18 required" if v and int(v) < 18 else None],
})
if errors:
    return {"errors": errors}, 422
```

**Edge cases**

- If you supply a callable that expects `(field, value, data)`, it will be passed all three when supported; otherwise `(field, value)`.
- If your rule raises, it is caught and added as `"<field>: validation error"`.
- String rules depend on your `get_rule()` registry—ensure they’re registered in your app.

---

## Binding to dataclasses

`bind_to(cls, defaults: dict = {}, cast: bool = True)`

- Requires `cls` to be a `@dataclass`.
- Gathers `req.all()`; normalizes list keys ending with `[]` to match fields without the brackets.
- Attempts to cast each field to the dataclass‑declared type.
  - Lists: if field type is `list[T]`, converts comma‑separated strings to lists and casts each element to `T`.
- Adds `obj.as_dict()` at runtime for convenience.

**Example**

```python
@dataclass
class Search:
    q: str = ""
    page: int = 1
    tags: list[str] = None

model = req.bind_to(Search, defaults={"tags": []})
```

**Edge cases**

- Non‑castable values are left as‑is (no exception raised).
- Only dataclasses are supported (otherwise `ValueError`).

---

## URL helpers

- `path()`, `url()`
- `clean_url(request, key, value=None)` → returns the current path with query param `key` removed (or replaced with `value` if provided)

**Note on signature:** `clean_url` is defined to accept a **request instance** as its first argument, not `self`. Call it like:

```python
req = Request()
next_page_url = Request.clean_url(req, "page", value=3)
```

---

## Accessing raw aggregates

- `all()` merges `view_args`, `args`, `form`, and JSON (if `Content-Type: application/json`) into one dict.
- `only(keys)` / `except_(keys)` filters that aggregate.

**Lists**

- Keys ending with `[]` are preserved with their list values by re‑reading from `request.args.getlist(key)`.

---

## Security & reliability best practices

1. **Input casting**: use typed accessors (`integer`, `float`, `boolean`) or `input(..., cast=...)` to keep your views clean and predictable.
2. **Dates/times**: always parse with a known timezone and store UTC; only localize for display.
3. **Validation**: centralize rule definitions (`get_rule`) and include a test for each rule; treat any validation exception as a 400/422 with a safe error message.
4. **Files**: never trust filenames; generate unique names, validate type/size, and store outside the web root.
5. **CSRF**: enforce on every state‑changing POST/PUT/PATCH/DELETE route.
6. **Content negotiation**: branch responses based on `expects_json()` to avoid mixing HTML with API semantics.
7. **Flash + old()**: on validation failures, flash inputs and redirect using PRG (Post/Redirect/Get) to prevent duplicate submissions.
8. **Sanitize**: use `sanitize()` on any field you might later render unescaped.
9. **Feature flags**: use `when_has` / `when_filled` to conditionally add filters to queries without deeply nested `if`s.

---

## Common patterns

### Search with optional filters

```python
q = base_query
q = req.when_filled("q", lambda v: q.where_like("name", f"%{v}%"), default=q)

if req.boolean("active") is True:
    q = q.where("active", "=", 1)

created_from = req.date("created_from")
created_to = req.date("created_to")
if created_from and created_to:
    q = q.where_between("created_at", created_from, created_to)
```

### Bulk filter UI using `grouped()`

```html
<input name="filters[0][field]" value="amount">
<input name="filters[0][operator]" value=">=">
<input name="filters[0][value]" value="50000">
```

```python
for f in req.grouped("filters"):
    q = q.where(f["field"], f.get("operator", "="), f.get("value"))
```

### Safe pagination links

```python
page = max(1, req.integer("page", 1))
prev_url = Request.clean_url(req, "page", value=page-1) if page > 1 else None
next_url = Request.clean_url(req, "page", value=page+1)
```

---

## Edge cases & gotchas

- **JSON parsing**: `__get_json()` only returns `request.json` when `Content-Type` is exactly `application/json`. Clients sending `application/json; charset=utf-8` will still work in Flask, but if a proxy mutates headers, ensure the content type is preserved.
- **Boolean casting**: only the literals `true, 1, yes, on` (case‑insensitive) map to `True`. Everything else (including `"false"`, `"0"`) maps to `False`.
- **Datetime parsing**: if you parse without `tz`, naive values are assumed to be in the given `tz` and are **converted to UTC** by default (`to_utc=True`). Pass `to_utc=False` to keep local timezones.
- ``: ignores keys without at least 2 bracket levels and non‑numeric indexes. Ensure your UI emits `name[index][field]` with numeric `index`.
- ``** vs **``: `lists()` re-reads only `[]` keys from the query string; `to_list()` splits strings by comma.
- **Uploaded file size**: calling `size()` may advance the stream; seek back before `save()` if needed.
- ``** signature**: static-like method; call as `Request.clean_url(req, key, value)`.
- **Validation rules**: string rules depend on your app’s `get_rule()` registry. Missing rules are silently skipped; consider adding a startup check to ensure rules are registered.

---

## API reference (selected)

### Retrieval & casting

- `input(key, default=None, cast=None)`
- `query(key, default=None)`
- `string(key, default=None)` / `integer(key, default=None)` / `float(key, default=None)`
- `to_list(key, default=None, cast=str)` / `lists()`

### Presence & branching

- `has/has_any/has_all/has_only`
- `filled/is_not_filled/any_filled`
- `when_has/when_filled/missing/when_missing`

### Dates & times

- `date(key)` / `datetime_(key, tz="UTC", to_utc=True)` / `time(key)`
- `now/today/tomorrow/yesterday/days_ago/days_in_future/weeks_ago`
- `start_of_week/start_of_month/end_of_month/months_ago`

### Grouping

- `form(group)`
- `grouped(prefix=None, sort=True, as_list=True)`

### Request info

- `path/url/method/is_method/host/ip/ips`
- `headers/get_acceptable_content_types/accepts/expects_json/get_locale`

### Files

- `file/has_file/is_image`
- `UploadedFile.save/extension/path/mimetype/size/filename`

### Cookies, session & flash

- `session/cookie/has_cookie`
- `flash/flash_only/flash_except/old`

### Security & validation

- `csrf_token/validate_csrf`
- `sanitize`
- `validate(schema)`

### Data binding

- `bind_to(dataclass, defaults={}, cast=True)`

### URL utilities

- `clean_url(request, key, value=None)`

---

## README format choice: `.md` vs `.docx` vs `.txt`

- **README.md (Markdown)** — **Recommended** for code repos. Pros: first‑class on GitHub/GitLab, inline code blocks, headings/TOC via renderers, easy diffing, embeddable links and images. Supports long documents and can be split into `/docs` for deeper guides.
- **README.docx** — richer formatting (true TOC, page layout) but poor diffability, not friendly for PR reviews, and clunky in terminals/IDE viewers.
- **README.txt** — universally readable but no structure, no code formatting, and hard to navigate for long docs.

**Conclusion:** Keep `` as your canonical entry point. If you need a longer “User Guide,” create `/docs/request-guide.md` and link it from the README. For stakeholders who insist on Word, auto‑export Markdown to `.docx` in your release pipeline.

---

## Migration checklist for production usage

-

---

## Changelog notes (for your project)

- Document any new date/time formats added to parsers
- Record changes to boolean casting rules
- Note signature changes (e.g., if `clean_url` becomes an instance method)

---

*Last updated: 2025‑08‑10*

