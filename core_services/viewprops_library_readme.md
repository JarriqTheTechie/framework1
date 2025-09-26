# ViewProps

A tiny, pragmatic helper for packaging variables from your current function into a dictionary that you can pass to templates (views) or JSON APIs.

> In one line: **return everything in the current function’s local scope** (minus a few filtered keys), so you don’t have to hand‑assemble context dictionaries.

---

## Why ViewProps?

Building view contexts usually turns into repetitive boilerplate:

```python
return render_template("invoice.html", title=title, invoice=invoice, items=items, total=total)
```

`ViewProps` removes that friction:

```python
view_props = ViewProps
# ... define title, invoice, items, total, etc.
return render_template("invoice.html", **view_props.compact())
```

No more manually listing every key. Cleaner functions, fewer mistakes.

---

## What it actually does

- **Introspects the caller’s local variables** using `inspect.stack()[1][0].f_locals`.
- **Filters out** any keys that:
  - start with `"__"` (dunder internals), and
  - for `compact()` only: the helper itself under the key `"view_props"` (see Best Practices).
- **Optionally filters** by an allowlist or blocklist with `api_compact()`.

There is **no retained state**; methods are `@classmethod`s. The class is decorated with a `@singleton`, but the API is class‑based and stateless.

> **Note about UI DSL objects**: You may notice imports for `Heading`, `Button`, `Table`, etc. There’s a commented block in `compact()` that would inject those classes into the returned dict. It’s intentionally disabled by default. If you want those available in your templates via `compact()`, you can explicitly add them to your context (see Examples) or uncomment that block in your copy.

---

## Installation / Import

Add `ViewProps.py` to your project or install it with your Framework1 codebase. Then import:

```python
from ViewProps import ViewProps           # if the file is in your app root
# or, if packaged:
# from framework1.core_services.ViewProps import ViewProps
```

> Use the import path that matches where the file lives in your project.

---

## API

### `ViewProps.compact() -> dict`

Capture **all** locals from the **immediate caller** and return them as a dictionary for use with `**kwargs`.

**Important behavior**

- Removes keys that start with `"__"`.
- **Deletes** the key `"view_props"` unconditionally.
- Uses the **immediate caller** frame (`stack()[1]`).

**When to use**

- Rendering HTML templates where you want to pass *everything* from the current function.

### `ViewProps.api_compact(exclude_keys: list[str] = None, include_keys: list[str] = None) -> dict`

Like `compact()`, but only returns filtered keys and **does not** attempt to delete `"view_props"` directly (so it won’t raise if you didn’t define it).

**Rules**

- Filters out keys starting with `"__"` and the literal key `"view_props"`.
- If `include_keys` is provided, **only** keys in that allowlist are returned (minus any `exclude_keys`).
- If `include_keys` is omitted, everything except `exclude_keys` is returned.

**When to use**

- Building JSON API payloads where you want to control exactly which fields are exposed.

---

## Best practices

1. **Always declare **``** in the same scope** where you call `compact()`.

   - `compact()` does `del props['view_props']` without a safety check. If you didn’t define a local named `view_props`, it will raise a `KeyError`.
   - Declaring a local `view_props` prevents that.

2. **Call from the scope that owns the variables.**

   - `inspect.stack()[1]` captures the *immediate* caller. If you wrap `compact()` in a helper function, you’ll collect the wrapper’s locals—not your view’s locals.

3. **Be intentional with what’s in your locals.**

   - `compact()` will return *everything* in your local scope. Avoid leaving sensitive objects (connections, secrets) in locals right before calling it.

4. **Prefer **``** for APIs.**

   - Use `include_keys` (allowlist) for outward‑facing payloads to avoid leaking internal variables.

5. **Name private variables with a single underscore if you want to exclude them manually.**

   - Only `"__dunder"` names are auto‑filtered. Single underscore names (`_temp`) will be included unless you exclude them.

6. **Serializability for JSON**

   - `compact()`/`api_compact()` happily return functions, DB cursors, etc. If you `jsonify` that dict, serialization may fail. Use `include_keys` to select JSON‑safe values.

7. **Keep performance in mind.**

   - `inspect.stack()` is fast enough for typical request/response, but don’t call `compact()` inside tight loops.

---

## Usage patterns & examples

### 1) Flask controller → Template

```python
from flask import render_template
from ViewProps import ViewProps

@app.get("/invoices/<int:id>")
def show_invoice(id):
    view_props = ViewProps  # required for compact()

    invoice = svc.get_invoice(id)
    items = svc.get_items(id)
    title = f"Invoice #{id}"

    return render_template("invoice.html", **view_props.compact())
```

### 2) Template + bringing in UI DSL classes explicitly

```python
view_props = ViewProps
Heading = ui.Heading
Button = ui.Button

# ... other locals you want available in the template ...
return render_template("page.html", **view_props.compact())
```

> Alternatively, modify your local copy of `ViewProps.compact()` to re‑enable the commented block that injects `Heading`, `Subheading`, `Button`, `ModalButton`, `Table`, and `Dropdown`.

### 3) JSON API with allowlist (recommended)

```python
from flask import jsonify
from ViewProps import ViewProps

@app.get("/api/search")
def search():
    # locals you compute
    query = request.args.get("q", "")
    page = int(request.args.get("page", 1))
    per_page = 20
    results = svc.search(query, page, per_page)
    total = results.total

    # Only expose selected keys
    payload = ViewProps.api_compact(include_keys=["query", "page", "per_page", "total", "results"])
    return jsonify(payload)
```

### 4) JSON API with blocklist

```python
payload = ViewProps.api_compact(exclude_keys=["db", "secret", "internal_state"])  # everything else goes out
return jsonify(payload)
```

### 5) Avoiding `KeyError` without declaring `view_props`

Use `api_compact()` if you can’t (or don’t want to) bind `view_props`:

```python
# No local `view_props` defined
return render_template("report.html", **ViewProps.api_compact())
```

### 6) Ensuring the right scope

Don’t do this:

```python
def render_page():
    def ctx():
        view_props = ViewProps
        return view_props.compact()  # captures locals of ctx(), not render_page()

    title = "Dashboard"
    return render_template("page.html", **ctx())  # title is missing
```

Do this instead:

```python
def render_page():
    view_props = ViewProps
    title = "Dashboard"
    return render_template("page.html", **view_props.compact())
```

### 7) Mixing allowlist and blocklist

If both are provided to `api_compact()`, **allowlist wins**, but any keys in `exclude_keys` are still removed:

```python
ViewProps.api_compact(include_keys=["a", "b", "c"], exclude_keys=["b"])  # → returns only {"a", "c"}
```

---

## Edge cases & gotchas

- ``** in **``

  - You didn’t create a local variable named `view_props` before calling. Fix by adding `view_props = ViewProps` in the same scope—or use `api_compact()` instead.

- **Nested/wrapped calls don’t see your variables**

  - `compact()` reads the **immediate** caller. If you call it from inside a helper function, it won’t capture your view’s locals. Call it directly in your view function.

- **Leaking large or sensitive objects**

  - `compact()` returns everything. If a cursor, connection, or secret is in your locals, it’ll be included. Prefer `api_compact(include_keys=...)` or explicitly `del` unwanted locals before calling.

- **Single underscore variables are included**

  - Only `__dunder` names are filtered automatically. Use `exclude_keys` or rename temporary values with a double underscore if you want auto‑filtering.

- **Non‑serializable objects in APIs**

  - `jsonify(ViewProps.compact())` may break if locals include objects JSON can’t serialize. Use `api_compact(include_keys=...)` with only JSON‑safe values.

---

## Testing quick checks

- **Template**: Add a debug block

  ```jinja2
  <pre>{{ props | tojson(indent=2) }}</pre>
  ```

  and call your view with:

  ```python
  props = ViewProps.api_compact(include_keys=["title", "invoice", "items"])  # or compact()
  return render_template("page.html", props=props, **props)
  ```

- **Unit test**: Simulate a caller frame

  ```python
  def make_context():
      view_props = ViewProps
      a, b = 1, 2
      return view_props.compact()

  assert make_context() == {"a": 1, "b": 2}
  ```

---

## FAQ

**Q: Why not accept explicit variable names (like PHP’s **``**)?** A: This helper is designed for fast, boilerplate‑free view context generation. If you want explicit control per call, prefer `api_compact(include_keys=[...])`.

**Q: Can I safely use it in async code or threads?** A: It simply reads the current call stack. There’s no global state; usage is safe, but always be mindful of performance in hot paths.

**Q: What about adding the UI DSL (Heading, Button, Table) to every template automatically?** A: Either uncomment the block in `compact()` that injects those classes, or set them as locals before calling `compact()` (see Example 2).

---

## Change ideas (if you choose to extend)

- Make `compact()` safer by using `props.pop('view_props', None)` instead of `del` to remove the helper.
- Add an optional `prefix` parameter to strip/namespace local keys.
- Add a `serialize` callable to transform values before returning (useful for API output).

---

## TL;DR

Use `compact()` when rendering templates and you want to pass everything in scope. Use `api_compact()` for APIs or when you need fine‑grained control. Always declare `view_props = ViewProps` before calling `compact()` in the same function. Keep your locals clean.

