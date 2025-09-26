# Form DSL — Comprehensive Guide

This document explains how to build and render forms with the Form DSL. It covers field types, validation, grouping, rendering, best‑practice patterns, and edge cases observed in the current implementation.

> The Form DSL is intentionally lightweight: you declare a `Form` subclass, return a schema of fields and groups, set the action/method/submit button, and call `render()` to get HTML. Validation is declarative and attached to fields.

---

## Contents

- [Quick start](#quick-start)
- [Core concepts](#core-concepts)
  - [Form](#form)
  - [Fields](#fields)
  - [Field groups](#field-groups)
  - [Validation](#validation)
- [Field reference](#field-reference)
  - [TextField](#textfield)
  - [TextareaField](#textareafield)
  - [SelectField](#selectfield)
  - [CheckboxField](#checkboxfield)
  - [RadioField](#radiofield)
  - [RawField](#rawfield)
- [Rendering & Actions](#rendering--actions)
- [Advanced techniques](#advanced-techniques)
  - [Dynamic label/help text](#dynamic-labelhelp-text)
  - [Value transformation (](#value-transformation-modify_using)[`modify_using`](#value-transformation-modify_using)[)](#value-transformation-modify_using)
  - [Defaults](#defaults)
  - [Per‑field data attributes & inline JS](#per-field-data-attributes--inline-js)
  - [Visibility & disabled/readonly](#visibility--disabledreadonly)
  - [Styling hooks](#styling-hooks)
- [Best practices](#best-practices)
- [Edge cases & notes](#edge-cases--notes)
- [End‑to‑end example (Flask)](#end-to-end-example-flask)

---

## Quick start

```python
# forms/user_form.py
from framework1.dsl.FormDSL.Form import Form
from framework1.dsl.FormDSL.FieldGroup import FieldGroup
from framework1.dsl.FormDSL.TextField import TextField
from framework1.dsl.FormDSL.TextareaField import TextareaField
from framework1.dsl.FormDSL.SelectField import SelectField
from framework1.dsl.FormDSL.CheckboxField import CheckboxField
from framework1.dsl.FormDSL.RadioField import RadioField

class UserForm(Form):
    def schema(self):
        return [
            FieldGroup(
                title="Account",
                fields=[
                    TextField("email")
                        .set_label("Email address")
                        .set_class("form-control")
                        .set_label_class("form-label")
                        .is_required("Email is required.")
                        .pattern(r"^[^@]+@[^@]+\.[^@]+$", "Provide a valid email."),

                    TextField("password")
                        .set_field_type("password")
                        .set_label("Password")
                        .set_class("form-control")
                        .min_length(8, "Use at least 8 characters."),
                ],
            ),

            FieldGroup(
                title="Profile",
                fields=[
                    TextField("name")
                        .set_label("Full name")
                        .set_class("form-control")
                        .is_required(),

                    SelectField("country")
                        .set_label("Country")
                        .set_class("form-select")
                        .set_options([
                            ("BS", "Bahamas"),
                            ("US", "United States"),
                            ("CA", "Canada"),
                        ])
                        .is_required("Select a country."),

                    RadioField("gender")
                        .set_label("Gender")
                        .set_outer_class("form-check mb-2")
                        .set_options([("M", "Male"), ("F", "Female"), ("X", "Prefer not to say")]),

                    TextareaField("bio")
                        .set_label("Short bio")
                        .set_rows(4)
                        .set_class("form-control")
                        .max_length(500, "Keep it under 500 characters."),
                ],
            ),

            FieldGroup(
                title="Preferences",
                fields=[
                    CheckboxField("topics")
                        .set_label("Topics of interest")
                        .set_outer_class("form-check mb-1")
                        .set_options([
                            ("aml", "AML/Compliance"),
                            ("fintech", "FinTech"),
                            ("security", "Security"),
                        ]),
                ],
            ),
        ]
```

In your route/controller, instantiate with incoming data and render:

```python
# app.py (Flask)
from flask import render_template, request
from forms.user_form import UserForm

@app.get("/users/new")
def users_new():
    form = UserForm(data={})\
        .set_form_action("/users")\
        .set_method("POST")\
        .set_submit_button_text("Create user")\
        .set_submit_button_class("btn btn-primary")
    return render_template("base.html", body=form.render())

@app.post("/users")
def users_store():
    form = UserForm(data=request.form.to_dict())\
        .set_form_action("/users")\
        .set_method("POST")
    if not form.validate():
        # Re-render with errors and old input
        form.set_submit_button_text("Create user")
        return render_template("base.html", body=form.render()), 422

    # Do something with form.data ...
    return redirect("/users")
```

---

## Core concepts

### Form

Create a subclass of `Form` and override `schema()` to return a list of fields and/or `FieldGroup` blocks. You can then fluently configure:

- `set_method("POST"|"GET"|...)`
- `set_class("...")` / `set_style("...")`
- `set_enctype("multipart/form-data")` for uploads
- `set_submit_button_text(...)`, `set_submit_button_class(...)`, `set_submit_button_style(...)`
- `set_form_action(url_or_callable, **kwargs)` — if you pass a Flask view function, the action is resolved via `url_for()`
- `set_data(dict)` — replace the data backing the form
- `visible_on(bool)` — show/hide the entire form
- `detect_form_action(data, store_action, update_action)` — automatically choose action/text based on the presence of an id

### Fields

Every field derives from `BaseField` and supports these fluent setters:

- Content & labeling: `set_label(str|callable)`, `set_help_text(str|callable)`
- CSS & layout: `set_class(...)`, `set_label_class(...)`, `set_style(...)`, `set_outer_class(...)`
- Attributes: `set_data_attribute(key, value, js_inline=False)`
- UX & visibility: `set_readonly(True)`, `set_disabled(True)`, `visible_on(bool)`
- Value helpers: `default(value)`, `modify_using(callable)`
- Validation: `is_required(...)`, `min_length(n, ...)`, `max_length(n, ...)`, `pattern(regex, ...)`, `add_validation(fn, message)`

### Field groups

`FieldGroup(title, fields, description=None, collapsible=False)` groups fields and can carry its own CSS classes/styles. Values for grouped fields are resolved using the field name directly, and dotted names (e.g., `billing.address`) are supported inside groups when your data is nested dictionaries.

Chainable configuration:

- `set_title_class`, `set_description_class`, `set_field_container_class`
- `set_class`, `set_style`
- `visible_on(bool)`
- `wrap_in_div_with_class_and_id(class_name, id="")` — wrap the whole group in a container

### Validation

Call `form.validate()` to evaluate all field rules. Errors are stored on `form.errors` as `{field_name: [messages...]}` and are rendered next to each field automatically when using `FieldGroup`. You can also embed `form.render_errors(name)` manually.

Add rules per field via:

```python
TextField("email")\
    .is_required("Email is required.")\
    .pattern(r"^[^@]+@[^@]+\.[^@]+$", "Provide a valid email.")

TextField("username")\
    .add_validation(lambda v: v.isalnum(), "Only letters and numbers.")
```

---

## Field reference

### TextField

- Base single‑line input. Defaults to `type="text"`.
- Use `.set_field_type("password"|"email"|"number"|...)` to switch the HTML type.

**Example**

```python
TextField("email").set_field_type("email").set_label("Email").is_required()
```

### TextareaField

- Multiline input. Use `.set_rows(n)` to change height.
- Help text and label classes are supported.

**Example**

```python
TextareaField("notes").set_label("Notes").set_rows(6).set_class("form-control")
```

### SelectField

- Dropdown with options supplied as:
  - `[(value, label), ...]`
  - `["value1", "value2"]` (value == label)
  - `[{"value": "A", "label": "Option A"}, ...]`
  - Optgroups: `{ "group": "Group label", "options": [{"value": "X", "label": "X"}, ...] }`

**Example**

```python
SelectField("country").set_options([
    ("BS", "Bahamas"),
    {"group": "North America", "options": [
        {"value": "US", "label": "United States"},
        {"value": "CA", "label": "Canada"},
    ]},
])
```

### CheckboxField

- Renders one or more checkboxes. The submitted name is `name[]` to support multiple values.
- Use `.set_outer_class("form-check")` to control the wrapper class for each item.

**Example (multi‑select)**

```python
CheckboxField("topics").set_options([
    ("aml", "AML/Compliance"),
    ("fintech", "FinTech"),
])
```

> **Note**: For a single boolean toggle, you can still use `CheckboxField` with a single option (you’ll receive a list). Alternatively, prefer a `RadioField` for yes/no.

### RadioField

- Same API as `CheckboxField`, but renders `<input type="radio">` and posts a single scalar value.

**Example**

```python
RadioField("status").set_options([("active", "Active"), ("inactive", "Inactive")])
```

### RawField

- Outputs a pre‑formatted value without surrounding input/label. Useful for read‑only fragments, headings, or custom HTML snippets you compute with `modify_using`.

**Example**

```python
from framework1.dsl.FormDSL.BaseField import RawField
RawField("hr").modify_using(lambda v, record: "<hr class='my-4'>")
```

---

## Rendering & Actions

```python
form = (UserForm(data=data)
        .set_form_action(my_flask_view)   # or "\u002Fendpoint"
        .set_method("POST")
        .set_submit_button_text("Save")
        .set_submit_button_class("btn btn-primary"))

html = form.render()  # Safe to inject into your template
```

### Auto‑detecting create vs update

Override `get_id_key()` if your primary identifier isn’t `id`. Then:

```python
form.detect_form_action(data, store_action=my_create_view, update_action=my_update_view)
```

This sets the button text to *Create* or *Update* and wires the action accordingly based on whether `data[get_id_key()]` is present.

---

## Advanced techniques

### Dynamic label/help text

You may pass callables to `set_label` and `set_help_text`. They will be invoked at render time with `(record, data)` when available, which allows contextual captions.

```python
TextField("limit").
  set_label(lambda record, data: f"Limit (current: {data.get('current_limit', 'n/a')})").
  set_help_text(lambda record, data: "Used for monthly spend cap.")
```

> In `TextareaField`, help text is rendered from the stored string directly. If you need dynamic help for a textarea, compute it ahead of time and pass a string.

### Value transformation (`modify_using`)

`modify_using` lets you transform the value before rendering. Your function can accept `(value)` or `(value, record)`.

```python
TextField("name").modify_using(lambda v: (v or "").strip().title())
```

### Defaults

When a value is missing or empty, `default(value)` supplies a fallback used during rendering.

```python
TextField("currency").default("BSD")
```

### Per‑field data attributes & inline JS

```python
TextField("email")\
  .set_data_attribute("data-track", "signup")\
  .set_data_attribute("onchange", "console.log('changed');", js_inline=True)
```

Use `js_inline=True` to collapse multiline snippets to a single safe line. For `<select>`, `set_script("...")` will be wrapped into `<script>...</script>` automatically; for other fields, `set_script` appends raw content after the input — include `<script>` yourself if needed.

### Visibility & disabled/readonly

- `visible_on(False)` removes the field from output
- `set_disabled(True)` renders `disabled`
- `set_readonly(True)` renders `readonly`

### Styling hooks

- `set_class("form-control")` — input element classes
- `set_label_class("form-label")` — label element classes
- `set_outer_class("col-md-6")` — class applied to the field’s container div inside a `FieldGroup`
- `FieldGroup.set_field_container_class("mb-3")` — per‑field container within the group

---

## Best practices

1. **Always group your fields** — Use at least one `FieldGroup` for improved layout and to ensure submit button rendering occurs automatically.
2. **Validate at the field level** — Attach rules where you declare the field. Keep server‑side checks authoritative even if you add client‑side validation.
3. **Prefer semantic HTML types** — Use `TextField.set_field_type("email"|"password"|"number")` so browsers help with keyboards and validation.
4. **Avoid heavy logic in callables** — `set_label`/`set_help_text` and `modify_using` are executed during render; keep them fast.
5. **Normalize option values** — Make sure the `value` types you pass to `SelectField`/`RadioField` match the types in `data` (often strings) to get proper `selected`/`checked` behavior.
6. **Error placement** — Let `FieldGroup` handle `form.render_errors(name)` so each field shows its messages consistently.
7. **Accessibility** — Ensure labels are descriptive and use help text to clarify formats (e.g., date/time). Keep placeholders supplementary, not primary labels.

---

## Edge cases & notes

- **Submit button & non‑grouped fields**: The submit button is appended automatically when iterating groups; if your schema only contains standalone fields, add a final `FieldGroup` (even with an empty title) to ensure the submit button appears.
- **Checkbox vs. field container class**: For checkbox rendering styles, use `set_outer_class("form-check")` on the checkbox/radio fields themselves. Relying on automatic detection may not set the wrapper class as you expect.
- **Dotted names**: Inside `FieldGroup`, values for dotted keys like `billing.address` are resolved against nested dictionaries. Standalone fields outside groups don’t benefit from this dotted resolution.
- **Type matching for options**: `SelectField` compares equality with `==`. If your submitted data is an int but options use strings, cast consistently (e.g., store and compare strings).
- ``** on Textarea**: In the current `TextareaField` implementation, help text is read as a string; passing a callable won’t be invoked. Compute the string before calling `set_help_text`.
- **Inline script placement**: Only `SelectField` wraps `set_script(...)` in `<script>` tags. For other fields, include `<script>` yourself if you need to attach inline behavior.
- **Hidden fields**: Use `visible_on(False)` (or supply your own `RawField`) if you need to hide content. The low‑level `set_hidden(...)` flag is not intended for dynamic callbacks; prefer explicit visibility control and CSS classes.
- **Logging noise from **``: When `js_inline=True` in `set_data_attribute`, the collapsed JS is printed to stdout — be mindful in production environments.

---

## End‑to‑end example (Flask)

```python
from flask import Flask, request, render_template_string, redirect
from framework1.dsl.FormDSL.Form import Form
from framework1.dsl.FormDSL.FieldGroup import FieldGroup
from framework1.dsl.FormDSL.TextField import TextField
from framework1.dsl.FormDSL.TextareaField import TextareaField
from framework1.dsl.FormDSL.SelectField import SelectField
from framework1.dsl.FormDSL.CheckboxField import CheckboxField
from framework1.dsl.FormDSL.RadioField import RadioField

app = Flask(__name__)
app.secret_key = "dev"

class ProfileForm(Form):
    def get_id_key(self):
        return "user_id"

    def schema(self):
        return [
            FieldGroup(
                title="User",
                fields=[
                    TextField("user_id").set_label("ID").set_readonly(True),
                    TextField("email").set_label("Email").set_field_type("email").is_required(),
                    TextField("name").set_label("Name").is_required(),
                ],
            ),
            FieldGroup(
                title="Details",
                fields=[
                    SelectField("role").set_label("Role").set_options([("admin", "Admin"), ("user", "User")]).is_required(),
                    RadioField("active").set_label("Active?").set_options([("1", "Yes"), ("0", "No")]),
                    CheckboxField("tags").set_label("Tags").set_options([("vip", "VIP"), ("beta", "Beta Tester")]),
                    TextareaField("notes").set_label("Notes").set_rows(3),
                ],
            ),
        ]

@app.get("/profiles/<int:user_id>/edit")
def edit_profile(user_id):
    data = {"user_id": user_id, "email": "user@example.com", "name": "Jane"}
    form = ProfileForm(data).detect_form_action(
        data,
        store_action=create_profile,
        update_action=update_profile,
    ).set_submit_button_class("btn btn-primary")

    return render_template_string("""
    <html><body>
      <h1>Edit Profile</h1>
      {{ form|safe }}
    </body></html>
    """, form=form.render())

@app.post("/profiles")
def create_profile():
    form = ProfileForm(request.form.to_dict()).set_form_action(create_profile)
    if not form.validate():
        return render_template_string("<h1>Fix errors</h1>{{ form|safe }}", form=form.render()), 422
    # Create record ...
    return redirect("/profiles/1/edit")

@app.post("/profiles/<int:id>")
def update_profile(id):
    form = ProfileForm(request.form.to_dict()).set_form_action(lambda: update_profile)
    if not form.validate():
        return render_template_string("<h1>Fix errors</h1>{{ form|safe }}", form=form.render()), 422
    # Update record ...
    return redirect(f"/profiles/{id}/edit")

if __name__ == "__main__":
    app.run(debug=True)
```

---

## Changelog expectations

This README reflects the current behavior of the provided classes and is designed to be kept close to the code. If you add new field types or extend `Form.render`, revisit the **Edge cases & notes** section to keep guidance aligned with actual behavior.

