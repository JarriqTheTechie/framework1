# Table (Framework1 DSL)

A powerful, extensible table builder for Framework1 views. The `Table` class turns an ActiveRecord model (or any `QueryBuilder`) into a responsive, searchable, sortable, filterable, paginated HTML table with Bootstrap-friendly markup.

This guide shows:

- How to build tables quickly
- How search, sorting, filtering, and pagination work
- How to customize columns (badges, icons, links, audio, tooltips, truncation, HTML)
- How to use the utility columns (`IconColumn`, `Badge`, `Audio`)
- Best‑practice patterns for performance and safety
- Edge cases & limitations to be aware of

> **Assumptions**: You’re using Bootstrap 5 (for classes like `table`, `badge`, etc.) and an icon set such as Remix Icon or Font Awesome. The Table library renders small view snippets from `table-dsl/*.html`.

---

## Quick start

### 1) Basic Table bound to an ActiveRecord model

```python
from framework1.dsl.Table import Table, Field
from app.models import Payment  # ActiveRecord model

class PaymentTable(Table):
    model = Payment            # Table will create a query builder from your model
    table_class = "table table-striped table-hover mt-3"
    search_placeholder = "Search payments…"

    # Keep user selections in session
    persist_search = True
    persist_sort = True

    def schema(self):
        return [
            Field('id').label('ID').sortable().searchable().classes('text-nowrap'),
            Field('name').label('Payer').sortable().searchable(),
            Field('amount').label('Amount').classes('text-end fw-semibold').sortable(),
            Field('status').label('Status').badge().badge_color({
                'Pending': 'warning', 'Approved': 'success', 'Rejected': 'danger'
            }).sortable(),
            Field('created_at').label('Created').date("%Y-%m-%d").sortable(),
        ]

    def default_sort(self):
        return ('created_at', 'desc')  # Fallback sort
```

**Render in a view**

```python
# controller / view function
return render_template('payments.html', table=PaymentTable().paginate())
```

**Template**

```jinja2
{{ table|safe }}
```

This prints the search box, the table (with clickable sort headers), and a pager.

### 2) Table bound to a QueryBuilder (no model)

```python
from framework1.database.QueryBuilder import QueryBuilder
from framework1.dsl.Table import Table, Field

qb = QueryBuilder().set_driver('mysql').table('payments')

class PaymentsAdHoc(Table):
    model = None
    def __init__(self):
        super().__init__(non_activerecord_model=qb)
    def schema(self):
        return [Field('id').sortable(), Field('name').searchable(), Field('amount').sortable()]

# later
tbl = PaymentsAdHoc().paginate(page=1, per_page=20)
```

> **Note:** When using `non_activerecord_model`, pass a `QueryBuilder` that **already knows** its driver and table. It must support `.paginate()`.

---

## Column building (Field API)

Define columns by returning `Field` instances from `schema()` (or helpers that return `Field`). The most common options:

```python
Field('amount')
  .label('Amount')                # header text
  .classes('text-end')            # adds to <td> class
  .color('danger')                # adds `text-danger`
  .default('—')                   # value if null/empty
  .placeholder('N/A')             # alias of default()
  .sortable()                     # header becomes a sort link
  .searchable()                   # participates in search
  .date('%Y-%m-%d')               # formats strings, timestamps, or datetimes
  .limit(18, end='…')             # truncate by characters
  .words(10, end='…')             # truncate by words
  .html()                         # do not escape value (⚠ XSS risk)
  .url('/payments/{id}')          # wrap cell in <a href="…">
  .tooltip(lambda r: f"ID: {r.get('id')}")       # static or callable
  .badge()                        # wrap cell in <span class="badge">
  .badge_color({'High':'danger','Low':'secondary'})
  .icon('ri-cash-line')           # static icon or map: {'Approved':'ri-...'}
  .icon_color('success')
  .icon_position('left')          # 'left' (default) or 'right'
  .description(lambda r: r.get('note',''), position='below', limit=120)
  .extra_cell_attributes(lambda r: { 'data-id': str(r.get('id')) })
  .hidden(lambda r: r.get('archived') == 1)      # hide per-row
```

### Link templates & callables

- **Template**: `url('/users/{id}')` uses `record.to_dict()` for placeholders.
- **Callable**: `url(lambda r: f"/users/{r.get('id')}")` for full control.

### Descriptions

`description(text_or_callable, position='below', limit=100, end='…', html=False)` adds a muted, small text block below the main content. Use `html=True` to allow markup.

### Tooltips

Provide a string or a callable. Callables can accept `(record)` or `(record, data_dict)`.

### Hiding columns

- `hidden(True)` removes the column entirely.
- `hidden(lambda r: ...)` hides the cell for rows where the predicate returns `True`. (Headers never run callables, so the column header remains visible.)

> **Safety**: Prefer `.default('—')` over `.html()` when output could be user-provided. Only use `.html()` for trusted HTML.

---

## Utility columns

### `IconColumn`

A convenience wrapper that renders **only** an icon. Great for status or actions.

```python
from framework1.dsl.IconColumn import IconColumn

class PaymentTable(Table):
    def schema(self):
        return [
            IconColumn('status')
              .label('')
              .icon({ 'Approved': 'ri-checkbox-circle-line', 'Rejected': 'ri-close-circle-line' })
              .color({ 'Approved': 'success', 'Rejected': 'danger' })
              .size('fs-5')
              .tooltip(lambda r: r.get('status','Unknown'))
              .field(),                         # ← important: returns a Field for schema()
            Field('name').label('Payer'),
            # …
        ]
```

### `Badge`

A specialized field that always wraps the value in a Bootstrap badge. Use when you do not need `.badge()` on a regular `Field`.

```python
from framework1.dsl.Badge import Badge

Badge('priority').map([
    {'HIGH': 'bg-danger'},
    {'MEDIUM': 'bg-warning'},
    {'LOW': 'bg-success'},
])
```

> **Which to use?**
>
> - Use `Field(...).badge().badge_color({...})` when you also need other `Field` decorators (icons, links, tooltips, truncation).
> - Use `Badge(name)` when the cell is *only* a badge.

### `Audio`

Embeds an HTML `<audio>` player. Useful for voice notes, call recordings, etc.

```python
from framework1.dsl.Audio import Audio

Audio('audio_url').src(lambda r: r.get('audio_url'))\
    .type('audio/mp3').controls(True).autoplay(False).loop(False).muted(False)
```

---

## Search

The table renders a small search box. Searching works across:

- Columns marked with `.searchable()`
- Any columns returned by overriding `searchable()` on the table
- And `search_key` (string or list). Default is `'id'`.

**Behavior**

- Terms are split on spaces and applied with `AND` semantics: each term must match at least one searchable column.
- Set `persist_search = True` to keep the search string in session across navigation.

```python
class PaymentTable(Table):
    search_key = ['id','name','reference']
    def searchable(self):
        return ['payer_email','payer_account']
```

---

## Sorting

- Add `.sortable()` to a column to make its header clickable.
- Users can sort by multiple columns; the library appends columns to the `sort` query string.
- Use `default_sort()` as a fallback.
- Set `persist_sort = True` to keep sort in session.

```python
class PaymentTable(Table):
    def default_sort(self):
        return ('created_at', 'desc')
```

---

## Filtering

There are **two complementary** filtering systems:

### A) Ad hoc filters via query string (no UI code required)

Build your own "advanced search" UI or pass prebuilt filters in the request query string. Each condition is represented as:

```
filters[0][group]=Group A
filters[0][boolean]=AND         # AND | OR
filters[0][field]=amount
filters[0][operator]=greater_than
filters[0][value]=50000
```

**Supported operators**

- `where` (equals)
- `not_equal`
- `contains`, `starts_with`, `ends_with`
- `greater_than`, `less_than`, `greater_than_eq`, `less_than_eq`
- `in`, `not_in` (comma-separated values become a list)
- `between` (special handling for *date* ranges)
- `is_null`, `is_not_null`
- `regex`

The library groups your rows by `group` and nests conditions to preserve boolean precedence.

```python
# Example: two groups ( (A AND B) OR (C) )
?filters[0][group]=G1&filters[0][boolean]=AND&filters[0][field]=status&filters[0][operator]=in&filters[0][value]=Pending,Approved
&filters[1][group]=G1&filters[1][boolean]=AND&filters[1][field]=amount&filters[1][operator]=greater_than&filters[1][value]=1000
&filters[2][group]=G2&filters[2][boolean]=OR&filters[2][field]=created_at&filters[2][operator]=between&filters[2][value]=2024-01-01,2024-12-31
```

> **Tip**: `between` is optimized for **dates**; on OR groups it may fall back to a non-between path depending on your QueryBuilder. Prefer AND groups or use explicit `>=` / `<=` when combining with OR.

### B) Built-in Filter UI (Offcanvas Builder)

If your table class defines a `filters()` method that returns `Filter` objects **or** if you set `filterable_fields`, the table renders an offcanvas **Filter Builder** (opens from the right). It supports grouping, AND/OR chaining, and serializes to the same `filters[...]` format above. It includes a **Reset** link that clears all filter query params.

```python
class PaymentTable(Table):
    filterable_fields = ['status','amount','created_at']   # shows the filter bar
    def filters(self):
        from framework1.dsl.TableFilter import Filter
        return [
            Filter.make('status').label('Status').options(['Pending','Approved','Rejected']),
            Filter.make('amount').label('Amount'),
            # ...
        ]
```

> **Persisting filters**: If you want to remember individual filter values, set `persist_filters = True` and give your `Filter` keys unique names. (Ungrouped filters are applied directly; grouped filters currently prefer AND semantics.)

---

## Pagination

Call `.paginate(page=None, per_page=None)` on the table. It reads `page`/`per_page` from the request by default, and renders a minimal pager:

- Shows “Previous/Next” links
- Displays “Showing X of Y items”

**Best practice**

- Always paginate when the dataset can grow (avoid `get()` without `paginate()`).
- For MSSQL, ensure your query has an `ORDER BY` before pagination; the library will attempt to order by your primary key automatically.

```python
PaymentTable().paginate(page=1, per_page=25)
```

---

## Row selection & bulk actions

Set `selectable = True` to render a *select-all* checkbox in the header and one per row. The table will emit checkbox values with the key id (default `'id'`, configurable via `set_key_id('my_pk')`).

A scaffolded `/f1/delete-bulk` endpoint exists; wire it up to your own model mapping and authorization layer before using in production.

```python
class PaymentTable(Table):
    selectable = True
```

---

## Styling hooks

- `table_class`, `table_style` – applied to `<table>`
- `thead_class`, `tbody_class`, `tr_class` – applied to `<thead>`, `<tbody>`, `<tr>`

---

## Extending the table

### Add a double‑click row action

If your table implements `record_url(record)` which returns JavaScript (e.g., `window.location='…'`), rows will get an `ondblclick` handler automatically.

```python
class PaymentTable(Table):
    def record_url(self, record):
        return f"window.location='/payments/{record.get('id')}'"
```

### Replace or extend the partials

The following view snippets are rendered internally. You can customize them by overriding templates with the same names:

- `table-dsl/search.html` – search input
- `table-dsl/pagination.html` – pager
- `table-dsl/filter-bar.html` + `table-dsl/filter-bar-styles.html` – offcanvas filter builder

---

## Cookbook

### Colored text + badge + tooltip + link

```python
Field('status')\
  .label('Status')\
  .color({'Approved':'success','Rejected':'danger'}.get)\
  .badge().badge_color({'Approved':'success','Rejected':'danger'})\
  .tooltip(lambda r: f"Changed: {r.get('updated_at','—')}")\
  .url(lambda r: f"/payments/{r.get('id')}")
```

### Truncated HTML content with description

```python
Field('message').html().limit(120).description(lambda r: r.get('note',''))
```

### Date range filtering via query string

```
?filters[0][group]=Date&filters[0][boolean]=AND&filters[0][field]=created_at&filters[0][operator]=between&filters[0][value]=2025-01-01,2025-01-31
```

### Search across multiple fields

```python
class UsersTable(Table):
    search_key = ['id','email','username']
    def searchable(self):
        return ['first_name','last_name']
```

---

## Best practices

1. **Always paginate** large datasets.
2. **Whitelist **``** fields** to keep search fast. Backed by DB indexes where possible.
3. **Prefer **`` for missing values instead of letting the cell go blank.
4. **Use **`` to normalize string/timestamp inputs; supply explicit formats in your UI (e.g., ISO dates).
5. **Avoid **``** unless trusted.** Consider sanitizing on write.
6. **Use **`` when an icon is the *entire* cell; it yields simpler markup and consistent alignment.
7. **Keep filters simple**: for OR-heavy date logic, prefer explicit `>=` / `<=` filters to avoid ambiguous “between” semantics.
8. **Persist user intent** (`persist_search`, `persist_sort`) for a better UX on back/forward navigation.
9. **Defer heavy logic to SQL**: do not prefetch all rows; let `QueryBuilder` push down `where`, `order_by`, and `paginate`.
10. **Audit bulk actions**: wire authorization and CSRF checks; never trust client‑side selection alone.

---

## Edge cases & limitations

- **Description position**: `description(..., position='above')` is accepted but presently renders below the main text in the default markup. If you need “above”, override the cell template or adjust your formatter to prepend text.
- ``** with OR**: The filter engine favors `where_between_dates` for date ranges. With `OR` groups, your `QueryBuilder` must support an `or_where_between_dates` equivalent or you should model ranges as `>=` and `<=`.
- ``** vs **``: Only `extra_cell_attributes(...)` is used to add attributes to `<td>`; `extra_attributes(...)` is currently a no‑op.
- **Header hiding**: `hidden(callable)` hides **cells** per‑row; headers do not evaluate callables (the column header remains).
- **Non‑ActiveRecord models**: You must pass a real `QueryBuilder` to `non_activerecord_model`. If the object lacks `.paginate()`, the table cannot auto‑page it.
- **HTML injection**: `.html()` disables escaping. Use with trusted content only.
- **Bulk delete scaffold**: The built‑in bulk delete route is scaffolding. You must provide model mapping and permission checks.

---

## Minimal API reference

### Table (selected attributes & hooks)

- `model`: ActiveRecord class **or** leave `None` and pass a `non_activerecord_model` (`QueryBuilder`) to the constructor.
- `table_class`, `table_style`, `thead_class`, `tbody_class`, `tr_class`.
- `key_id='id'` → `set_key_id('...')` to change checkbox value key.
- `search_key` (str or list), `search_placeholder` (str).
- `persist_search`, `persist_sort`, `persist_filters` (bool).
- `selectable` (bool) – toggles row checkboxes.
- Hooks: `schema()`, `default_sort() -> (field, dir)`, `searchable() -> list[str]`, `filters() -> list[Filter]`, `modify_table_query()` (mutate `self.query` if needed), `record_url(record) -> str`.
- Methods: `paginate(page=None, per_page=None)`, `render()` (returns Markup), `__str__()` → same as `render()`.

### Field

Key methods covered earlier. Callers often use: `label`, `classes`, `color`, `default`/`placeholder`, `icon`/`icon_color`/`icon_position`, `badge`/`badge_color`, `modify_using`, `date`, `html`, `description`, `limit`, `words`, `sortable`, `searchable`, `url`, `tooltip`, `extra_cell_attributes`, `hidden`.

### IconColumn / Badge / Audio

- `IconColumn(name).icon(...).color(...).size('fs-6').tooltip(...).field()`
- `Badge(name).map([{ 'Value':'bg-success' }])`
- `Audio(name).src(url).type('audio/mp3').controls(True).autoplay(False)...`

---

## Troubleshooting

- **Sorting not working**: ensure column has `.sortable()`. For MSSQL, verify you set a default sort or click a header to inject `ORDER BY` before paginating.
- **Search returns everything**: you did not mark columns as `.searchable()` and didn’t override `searchable()` or `search_key`.
- **Filters don’t apply**: inspect the URL – the offcanvas emits `filters[...][field/operator/value]` params. Make sure your fields match DB column names.
- **Icons not visible**: prefer `IconColumn` for pure-icon cells. If mixing text and icons in one cell, set `.icon('ri-...')` and `.icon_position('left'|'right')` on the `Field`.
- **HTML shows literally**: you forgot `.html()`.
- **Row dbl‑click not working**: implement `record_url(record)` to return JavaScript (e.g., a `window.location = '…'`).

---

## Contributing conventions

- Keep `schema()` small and readable; move heavy formatting to `modify_using()` callables.
- Keep Table classes stateless; prefer reading request state via `Request()`.
- Avoid eager `.get()` when `.paginate()` is available.
- Prefer mapping value→CSS using dicts (for badges, icons, colors) to keep presentation centralized.

---

## Example: Putting it all together

```python
class PaymentsDashboardTable(Table):
    model = Payment
    table_class = 'table table-striped table-hover align-middle'
    persist_search = True
    persist_sort = True
    selectable = True
    filterable_fields = ['status','amount','created_at','payer']

    def schema(self):
        from framework1.dsl.IconColumn import IconColumn
        from framework1.dsl.Badge import Badge

        return [
            IconColumn('status')
              .icon({'Approved':'ri-checkbox-circle-line','Pending':'ri-time-line','Rejected':'ri-close-circle-line'})
              .color({'Approved':'success','Rejected':'danger','Pending':'warning'})
              .size('fs-5')
              .tooltip(lambda r: r.get('status',''))
              .field(),

            Field('name').label('Payer').searchable().limit(32),

            Field('amount').label('Amount').classes('text-end fw-semibold').sortable()
                             .tooltip(lambda r: f"Ref: {r.get('reference','—')}")
                             .url(lambda r: f"/payments/{r.get('id')}"),

            Badge('priority').map([
                {'HIGH':'bg-danger'},{'MEDIUM':'bg-warning'},{'LOW':'bg-success'}
            ]),

            Field('created_at').label('Created').date('%b %d, %Y').sortable(),
        ]

    def searchable(self):
        return ['name','reference','payer_email']

    def default_sort(self):
        return ('created_at','desc')

    def record_url(self, record):
        return f"window.location='/payments/{record.get('id')}'"

# In your controller
return render_template('index.html', table=PaymentsDashboardTable().paginate())
```

---

That’s the Table DSL: focused, fast, and extensible. Build consistent data grids without sacrificing control over SQL, markup, or UX.

