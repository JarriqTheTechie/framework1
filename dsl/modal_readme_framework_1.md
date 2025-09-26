# Modal Library — Comprehensive Guide

> Server-side builders for Bootstrap 5 Modals and Slide‑Over (Offcanvas)

This library provides two tiny, chainable helpers that output ready-to-use Bootstrap markup:

- `Modal` — the standard centered dialog overlay.
- `ModalSlideOver` — a right-side slide‑over panel built on Bootstrap’s **offcanvas**.

Both builders return `markupsafe.Markup`, so you can safely inject the generated HTML into Jinja templates without double‑escaping.

---

## Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
  - [`Modal`](#modal)
  - [`ModalSlideOver`](#modalslideover)
- [Recipes](#recipes)
  - [Confirmation dialog](#confirmation-dialog)
  - [Form in a modal (with action buttons)](#form-in-a-modal-with-action-buttons)
  - [Slide‑over filter panel](#slideover-filter-panel)
- [Best Practices](#best-practices)
- [Edge Cases & Gotchas](#edge-cases--gotchas)
- [Testing Tips](#testing-tips)

---

## Prerequisites

- **Bootstrap 5** CSS & JS included on the page.
- **Jinja2** (or any renderer that respects `markupsafe.Markup`).

> The builders only output HTML. Showing/hiding relies on Bootstrap’s JS (via `data-bs-*` attributes or the Bootstrap JS API).

---

## Quick Start

```python
from framework1.dsl.Modal import Modal, ModalSlideOver  # adjust import as used in your app
from markupsafe import Markup

# Minimal footer button helper used in examples
class HtmlButton:
    def __init__(self, html: str):
        self._html = html
    def render(self) -> str:
        return self._html

user_modal = (
    Modal("userModal")
        .title("Edit user")
        .body(Markup("<p>Form goes here…</p>"))
        .footer_buttons([
            HtmlButton('<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>'),
            HtmlButton('<button type="submit" form="edit-user" class="btn btn-primary">Save changes</button>'),
        ])
        .modal_lg()
        .close_modal_by_clicking_away(False)  # static backdrop
)

# In your template
{{ user_modal }}  {# __str__ returns Markup; safe to inject #}

# A trigger somewhere on the page
# <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#userModal">Edit user</button>
```

> **Why **``**?** Pass `Markup("…")` for trusted HTML in `.body(...)`. If you have plain text, either escape it or let Jinja escape by default (see Best Practices).

---

## API Reference

### `Modal`

```python
Modal(modal_id: str)
```

Creates a new modal builder. `modal_id` must be **unique** on the page.

Chainable methods:

- `title(text: str)` — Sets the header title.
- `body(content: str | Markup)` — Sets the inner HTML of the modal body. Use `Markup` for trusted HTML.
- `footer_buttons(buttons: list)` — Expects a list of objects each exposing a `.render() -> str` method. The returned strings are injected into the footer.
- Size helpers (mutually exclusive — last call wins):
  - `modal_sm()`
  - `modal_md()` *(non‑standard in Bootstrap; useful as a custom class if you style it)*
  - `modal_lg()`
  - `modal_xl()`
  - `modal_fullscreen()`
- `close_modal_by_clicking_away(close_modal: bool = True)` — Controls backdrop behavior.
  - Pass `` to make the backdrop **static** (clicking outside does **not** close the modal).
  - Passing `True` (or omitting) keeps default Bootstrap behavior (click outside closes the modal).
- `render() -> Markup` — Returns the final HTML markup. `str(modal)` calls `render()` under the hood.

Generated structure (simplified):

```html
<div id="{id}" class="modal fade" tabindex="-1" [data-bs-backdrop="static"]>
  <div class="modal-dialog {size}">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">…</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">…</div>
      <div class="modal-footer">…footer buttons…</div>
    </div>
  </div>
</div>
```

---

### `ModalSlideOver`

A right-side slide‑over built with Bootstrap Offcanvas.

```python
ModalSlideOver(modal_id: str)
```

Chainable methods:

- `title(text: str)`
- `body(content: str | Markup)`
- `footer_buttons(buttons: list)` — **Note:** currently **ignored** in the rendered offcanvas (see Gotchas). Put action buttons inside the body instead.
- Size helpers (width breakpoints): `modal_sm()`, `modal_md()`, `modal_lg()`, `modal_xl()`, `modal_fullscreen()` → maps to `offcanvas-sm|md|lg|xl|xxl`.
- `close_modal_by_clicking_away(close_modal: bool = True)` — Pass `False` to set a static backdrop for offcanvas.
- `render() -> Markup`.

Generated structure (simplified):

```html
<div id="{id}" class="offcanvas offcanvas-end {size}" tabindex="-1" [data-bs-backdrop="static"]>
  <div class="offcanvas-header">
    <h5 class="offcanvas-title">…</h5>
    <button type="button" class="btn-close" data-bs-dismiss="offcanvas" aria-label="Close"></button>
  </div>
  <div class="offcanvas-body">…</div>
</div>
```

**Trigger HTML:**

```html
<button class="btn btn-outline-secondary" data-bs-toggle="offcanvas" data-bs-target="#filters">Open filters</button>
```

---

## Recipes

### Confirmation dialog

```python
confirm = (
    Modal("confirmDelete")
      .title("Delete record?")
      .body("This action cannot be undone.")
      .footer_buttons([
        HtmlButton('<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>'),
        HtmlButton('<button type="button" class="btn btn-danger" id="confirmDeleteBtn">Delete</button>'),
      ])
      .modal_sm()
)
```

Trigger and handler (example):

```html
<button class="btn btn-danger" data-bs-toggle="modal" data-bs-target="#confirmDelete">Delete</button>
<script>
  document.addEventListener('click', (e) => {
    if (e.target.id === 'confirmDeleteBtn') {
      // Perform delete (fetch/XHR), then close
      const modal = bootstrap.Modal.getInstance(document.getElementById('confirmDelete'));
      modal?.hide();
    }
  });
</script>
```

### Form in a modal (with action buttons)

```python
form_html = Markup('''
  <form id="edit-user" method="post">
    <!-- fields -->
  </form>
''')

edit_user = (
  Modal("editUser")
    .title("Edit User")
    .body(form_html)
    .footer_buttons([
      HtmlButton('<button class="btn btn-light" data-bs-dismiss="modal" type="button">Cancel</button>'),
      HtmlButton('<button class="btn btn-primary" form="edit-user" type="submit">Save</button>'),
    ])
    .modal_lg()
    .close_modal_by_clicking_away(False)
)
```

### Slide‑over filter panel

```python
filters = (
  ModalSlideOver("filters")
    .title("Filters")
    .body(Markup("<div>…filter controls…</div>"))
    .modal_md()
)
```

---

## Best Practices

- **Unique IDs**: Ensure each modal/offcanvas has a unique `modal_id`. Collisions will break triggers.
- **Escape by default**: If the body content originates from users, *don’t* wrap it in `Markup`. Let Jinja escape it, or sanitize upstream.
- **Use **``** for trusted HTML**: When you deliberately inject HTML (forms, components), wrap it in `Markup`.
- **Button contracts**: Objects passed to `.footer_buttons()` must expose `.render() -> str`. If you’re not using a button DSL, a tiny wrapper like `HtmlButton` (shown above) is sufficient.
- **One size at a time**: Call a single size helper per instance; the last size call takes precedence.
- **Static modals for destructive actions**: Use `.close_modal_by_clicking_away(False)` so accidental clicks don’t dismiss critical dialogs.
- **Defer heavy content**: For complex bodies, consider rendering minimal content first and lazy‑loading details after `shown.bs.modal` to keep pages snappy.

---

## Edge Cases & Gotchas

- ``** in **``: Buttons are currently **not rendered** in the slide‑over template. Put actions inside the body.
- **Keyboard (Esc) dismissal**: `.close_modal_by_clicking_away(False)` sets a static **backdrop** only. It does **not** disable Esc. If you must block Esc, add `data-bs-keyboard="false"` yourself (extend or post‑process the markup).
- ``** class**: Bootstrap doesn’t ship a `modal-md` size. It’s included here for symmetry/custom styling. If you don’t style it, it behaves like the default size.
- **Footer with no buttons**: The modal template always includes a footer `<div>`. That’s valid; if you prefer, pass an empty list to keep it clean.
- **Non‑renderable buttons**: Passing items without `.render()` to `.footer_buttons(...)` will raise an AttributeError. Stick to a known button DSL or the `HtmlButton` shim.
- **Content safety**: The builders don’t sanitize HTML. Treat `.body()` content responsibly.

---

## Testing Tips

- **String snapshot**: `str(Modal(...))` returns the final HTML; snapshot test against expected fragments (title, ids, classes).
- **Minimal DOM parse**: Use `BeautifulSoup` (or similar) to assert presence of `#id`, `.modal-dialog`, `.offcanvas-end`, and your footer buttons.
- **Behavior hooks**: In UI tests, assert that the correct `data-bs-*` attributes are present on triggers and that your destructive dialogs set a static backdrop when required.

---

## Reference

Public surface (chainable):

- `Modal(modal_id)`

  - `.title(text)`, `.body(content)`, `.footer_buttons(buttons)`
  - `.modal_sm()`, `.modal_md()`, `.modal_lg()`, `.modal_xl()`, `.modal_fullscreen()`
  - `.close_modal_by_clicking_away(close_modal: bool = True)`
  - `.render() -> Markup` and `__str__` returns Markup

- `ModalSlideOver(modal_id)`

  - `.title(text)`, `.body(content)`, `.footer_buttons(buttons)` *(ignored in output)*
  - `.modal_sm()`, `.modal_md()`, `.modal_lg()`, `.modal_xl()`, `.modal_fullscreen()` → `offcanvas-*`
  - `.close_modal_by_clicking_away(close_modal: bool = True)`
  - `.render() -> Markup` and `__str__` returns Markup

> If you need additional behaviors (e.g., disabling Esc, adding ARIA labels, or injecting extra attributes), consider extending the builders or post‑processing the returned `Markup` before injecting it into your template.

