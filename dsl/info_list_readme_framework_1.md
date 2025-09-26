# InfoList — Comprehensive Guide

A tiny, chainable DSL for rendering a **read-only details panel** ("info list") as Bootstrap-friendly HTML. Feed it a record (dict, ActiveRecord, or DataKlass), declare fields, and get semantically structured markup with labels, values, icons, badges, links, tooltips, and descriptions.

> This document covers **every public method** exposed by `InfoList` and `InfoListField`, recommended patterns, and known edge cases so you can deploy with confidence.

---

## At a Glance

```python
from framework1.dsl.InfoList import InfoList, InfoListField

class UserInfo(InfoList):
    def schema(self):
        return [
            InfoListField('full_name').label('Name').classes('fw-semibold'),
            InfoListField('email')
                .label('Email')
                .placeholder('—')
                .url(lambda r: f"mailto:{r.get('email','')}")
                .tooltip('Click to email'),

            InfoListField.separator(),  # visual separator (hr)

            InfoListField('status')
                .label('Status').badge()
                .badge_color({'Active': 'success', 'Suspended': 'warning', 'Closed': 'secondary'})
                .icon({'Active': 'ri-checkbox-circle-line', 'Suspended': 'ri-time-line', 'Closed': 'ri-close-circle-line'})
                .icon_position('left')
                .tooltip(lambda r: f"User is {r.get('status','Unknown')!s}"),

            InfoListField('joined_at')
                .label('Joined')
                .date('%b %d, %Y')  # see Date notes
                .color('muted'),

            InfoListField('bio')
                .label('About')
                .limit(140)  # characters
                .description(lambda r: r.get('bio',''), position='below', limit=120),
        ]

# Data can be a dict, ActiveRecord instance, DataKlass, or a list of dicts
user = {
    'full_name': 'Jada Rolle',
    'email': 'jada@example.com',
    'status': 'Active',
    'joined_at': '2024-03-18 10:22:00',
    'bio': 'Builder, parent, minimalist. Shipping useful things with a smile.'
}

html = UserInfo(user)\
    .set_heading('Account Overview')\
    .set_heading_class('d-flex align-items-center gap-2')\
    .set_icon('ri-user-3-line')\
    .set_footer('Updated automatically every 15 minutes')\
    .set_footer_class('small text-muted')\
    .set_field_infolist_label_classes('col-4 text-muted text-uppercase small')\
    .set_field_infolist_body_classes('col-8')\
    .render()

# or simply: str(UserInfo(user))
```

**Output structure (Bootstrap):**

```html
<div class="card my-3">
  <div class="card-header bg-white ..."><i class="ri-user-3-line nav_icon"></i> Account Overview</div>
  <div class="card-body">
    <div class="row">
      <div class="infolist-label col-4 ...">Name</div>
      <div class="infolist-body col-8 ...">Jada Rolle</div>
      <!-- etc -->
    </div>
  </div>
  <div class="card-footer text-muted ...">Updated automatically every 15 minutes</div>
</div>
```

> **Tip:** For Bootstrap tooltips to work, initialize them in your page once:
>
> ```js
> document.addEventListener('DOMContentLoaded', () => {
>   new bootstrap.Tooltip(document.body, { selector: '[data-bs-toggle="tooltip"]' });
> });
> ```

---

## Installing & Dependencies

- **Bootstrap** classes are used in markup (`card`, `row`, `col-*`, `badge`, etc.). Include Bootstrap CSS. Tooltips require Bootstrap JS.
- **markupsafe** is used to safely escape values unless you explicitly opt-in to `.html()` or `description(..., html=True)`.
- Works with plain dicts, `ActiveRecord` models, or `DataKlass` instances.

---

## Core Concepts

### 1) Create a subclass and implement `schema()`

Define the fields (order = render order). You can mix content fields and separators.

```python
class InvoiceInfo(InfoList):
    def schema(self):
        return [
            InfoListField('number').label('Invoice #').classes('fw-bold'),
            InfoListField('client').label('Client'),
            InfoListField('amount').label('Amount').currency().badge().badge_color('primary'),
            InfoListField('status').label('Status').badge().badge_color({
                'Paid': 'success', 'Overdue': 'danger', 'Draft': 'secondary'
            }),
            InfoListField.separator(),
            InfoListField('issued_at').label('Issued').date('%Y-%m-%d'),
            InfoListField('due_at').label('Due').date('%b %d, %Y'),
        ]
```

### 2) Provide data

- `dict` → `{'field': 'value'}`
- `ActiveRecord` → the model’s `.to_dict()` is used.
- `DataKlass` → also supported.
- `list[dict]` → will render *all* rows in the same card/body, one after the other. Prefer single-record usage for details panels.

### 3) Render

- `InfoList(data).render()` returns an HTML string.
- `str(InfoList(data))` calls `render()` under the hood.

---

## Field API (InfoListField)

> All field methods are chainable. Only `name` is required.

### Identity & Labeling

- `InfoListField('field_name')` — source key in your data.
- `.label(text_or_callable)` — header text or a callable `(value, record) -> str`.
- `.label_classes(css)` — classes applied to the **label cell**.
- `.classes(css)` — classes applied to the **value cell**.
- `.color('muted'|'primary'|...)` — shorthand to add `text-{color}` to value cell.

### Missing/Empty Values

- `.placeholder('—')` / `.default('—')` — value to show for `None`/empty strings.
- `.hide_if_empty()` — hide the field entirely when value is missing/empty.
- `.hidden(True|False|callable)` — hide unconditionally or with predicate `(value, record) -> bool`.

### Value Formatting

- `.modify_using(fn)` — transform `(value, record) -> str`.
- `.currency()` — formats with `$1,234.56` (best for numeric/Decimal).
- `.date(fmt)` — output using `datetime.strftime(fmt)`; accepts strings like `%b %d, %Y` or `%Y-%m-%d %H:%M`.
- `.limit(n, end='...')` — character limit.
- `.words(n, end='...')` — word limit.
- `.html()` — **do not escape** the value (you are responsible for safety).

### Icons & Badges

- `.icon('ri-check-line' | {'Approved': 'ri-check-line', ...})` — set a static icon or a map by value.
- `.icon_position('left'|'right')` — where the icon appears.
- `.icon_color('success'|'danger'|...)` — adds `text-{color}` to the icon `<i>`.
- `.badge()` — wrap content in `<span class="badge ...">`.
- `.badge_color('primary'|{'Paid': 'success', ...})` — static or per-value badge color (`bg-{color}`).

### Links, Tooltips, Descriptions

- `.url(template_or_callable)` — wrap the field in `<a href="...">`.
  - Template example: `'/users/{id}'` (placeholders use `record.to_dict()` keys)
  - Callable example: `lambda r: f"/invoices/{r.get('id')}"`
- `.tooltip(text_or_callable)` — adds `data-bs-toggle="tooltip" title="..."`.
  - Callable can be `(record) -> str` or `(record, data_dict) -> str`.
- `.description(text_or_callable, position='below', limit=100, end='...', html=False)` — small muted text under/over the value.

### Utility

- `InfoListField.separator()` — draw a horizontal rule between rows.

---

## List API (InfoList)

- `.set_heading(text_or_callable)` — optional card header.\*
- `.set_heading_class(css)` — classes for the header.
- `.set_icon(icon_or_callable)` — optional icon for the header.
- `.set_footer(text_or_callable)` — optional card footer.
- `.set_footer_class(css)` — classes for the footer.
- `.set_field_infolist_label_classes(css)` — default label column classes (fallback when a field has no `.label_classes()`).
- `.set_field_infolist_body_classes(css)` — default value column classes (fallback when a field has no `.classes()`).
- `.render()` — build the HTML string.

\* **Note:** these header/footer/icon helpers are currently presentation-only and accept either a static string or a callable receiving the *data object*.

---

## Practical Patterns & Best Practices

### Keep it to one record

`InfoList` shines as a **details panel**. Feed a single dict/model. If you pass a list, fields render for each item sequentially inside the same card—often not what you want for UX.

### Use badges for status-like fields

```python
InfoListField('status').label('Status').badge().badge_color({
    'Approved': 'success', 'Pending': 'warning', 'Rejected': 'danger'
})
```

### Prefer icon maps over a fixed icon

Value-mapped icons communicate meaning:

```python
InfoListField('risk').icon({'Low':'ri-shield-check-line','Medium':'ri-shield-line','High':'ri-shield-flash-line'})
```

### Trim aggressively

Use `.limit()` or `.words()` on free text to keep columns tidy. Add a `.description()` for an extended note when necessary.

### Safe HTML by default

Everything is escaped unless `.html()` is used. If you must inject HTML (e.g., colored fragments), sanitize beforehand.

### Rich links

Route users directly from fields:

```python
InfoListField('id').label('View').link('/invoice/', '')  # quick anchor builder
# or
InfoListField('id').url('/invoice/{id}')
```

### Tooltips for explanations

Great for terse labels with extra guidance:

```python
InfoListField('iban').label('IBAN').tooltip(lambda r: r.get('iban_note','No note'))
```

### Headings/footers as functions

Callables let the header/footer depend on the record:

```python
.set_heading(lambda data: f"Invoice {data[0]['number']}" if data else 'Invoice')
```

---

## End‑to‑End Example

```python
class PaymentInfo(InfoList):
    def schema(self):
        return [
            InfoListField('reference').label('Reference').classes('fw-semibold'),
            InfoListField('beneficiary_name').label('Beneficiary').placeholder('—'),
            InfoListField('amount').label('Amount').currency().badge().badge_color('primary')
                .tooltip(lambda r: f"Original currency: {r.get('currency','USD')}")
                .url(lambda r: f"/payments/{r.get('id')}")
                .icon({'USD':'ri-money-dollar-circle-line','EUR':'ri-money-euro-circle-line'}),
            InfoListField('status').label('Status').badge().badge_color({
                'Posted': 'success', 'Pending': 'warning', 'Failed': 'danger'
            }),
            InfoListField.separator(),
            InfoListField('created_at').label('Created').date('%Y-%m-%d %H:%M'),
            InfoListField('updated_at').label('Updated').date('%Y-%m-%d %H:%M')
                .hidden(lambda value, record: value == record.get('created_at')),
        ]

payment = {
    'id': 501,
    'reference': 'PAY-000501',
    'beneficiary_name': 'Acme Supplies',
    'amount': '7250',
    'currency': 'USD',
    'status': 'Posted',
    'created_at': '2024-05-14 10:43:00',
    'updated_at': '2024-05-14 10:43:00',
}

html = PaymentInfo(payment)\
    .set_heading('Payment Details')\
    .set_footer('Contact Treasury for reversals')\
    .set_field_infolist_label_classes('col-4 text-muted small')\
    .set_field_infolist_body_classes('col-8')\
    .render()
```

---

## Edge Cases, Limitations & Gotchas

> These notes reflect the current implementation so you can plan around sharp edges.

### 1) Date formatting tokens

`.date()` passes your format string directly to Python’s `strftime`. Use **Python tokens** (e.g., `%b %d, %Y`) instead of PHP-style (`M j, Y`). Using PHP tokens will render them literally.

### 2) Static icon on fields

When you call `.icon('ri-...')` on a field, the renderer currently references the **InfoList-level icon** property in one code path. To ensure icons render reliably, prefer **value-mapped icons** (`.icon({'Value':'ri-...'})`). If you must use a single icon on a field, also call `.set_icon('ri-...')` on the list as a fallback.

### 3) `extra_attributes` / `extra_cell_attributes`

These setters exist but are **not applied** to the generated markup in the current renderer. Treat them as reserved for future enhancements.

### 4) `sortable()` / `searchable()` flags

The flags can be set on fields but are **not used** by the renderer yet. They are markers for potential table/list integrations.

### 5) Tooltips require JS

`data-bs-toggle="tooltip"` is emitted, but you must initialize tooltips in JavaScript (see snippet above). Without it, the attribute is inert.

### 6) Multi-record data

Passing a list renders each record in sequence within the same card body. Use with caution; `InfoList` is optimized for a **single record** detail view.

### 7) URL template placeholders

`.url('/users/{id}')` formats with `record.to_dict()`. Missing keys cause the link to fall back to `href="#"`. Prefer callables when keys are optional.

### 8) Descriptions are sliced naïvely

`.description(..., limit=n)` truncates by **characters** without preserving word boundaries or HTML tag integrity. Use `limit` conservatively or pre-truncate your strings.

### 9) HTML safety

`.html()` and `description(..., html=True)` insert raw HTML using Markup. Ensure the content is trusted or sanitized upstream.

### 10) Currency formatting

`.currency()` uses U.S. dollar formatting by default (`$` symbol and 2 decimals). For multi‑currency contexts, prefer `.modify_using(...)` with your own formatter or include the ISO code in your label/value.

---

## Testing & Debugging Tips

- Build incrementally: start with a simple field and add features step by step.
- Use `.placeholder('—')` everywhere a value can be missing.
- Verify tooltips by hovering; if they don’t show, ensure Bootstrap JS is loaded and initialized.
- Inspect the generated HTML to confirm badge/icon classes and link hrefs.

---

## FAQ

**Q: Can labels depend on the value?**\
A: Yes. Pass a callable to `.label(lambda value, record: ...)`.

**Q: Can I render Markdown?**\
A: Not natively. Convert to HTML yourself and use `.html()` cautiously.

**Q: How do I hide a field based on another field?**\
A: Use `.hidden(lambda value, record: record.get('status') == 'Draft')`.

**Q: Can I paginate InfoList?**\
A: No; it’s a detail panel. Use your Table/List component for collections.

---

## Change Log Awareness

This guide maps to the exported `InfoList.py` you provided and may lag future changes. If upgrading, skim the file for new/altered methods and revisit the **Edge Cases** section.

---

## License & Credits

Part of the **Framework1** ecosystem. © You/your org. Use per your project’s license.

