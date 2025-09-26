
# ✅ Request Validation System

This module adds a Laravel-like validation system to your Flask `Request` class using composable, reusable rules.

---

## 🚀 Features

- Declarative schema-based validation
- Built-in rule registry (named rules like `"required"`, `"email"`, etc.)
- Parameterized rules (`min_length:8`, `confirmed:password`)
- Context-aware rules (cross-field comparison)
- Works with `Request.input()` and `Request.all()`

---

## 📦 Usage

### 1. Define a validation schema

```python
errors = request.validate({
    "Name": ["required"],
    "EmailAddress": ["required", "email"],
    "WebPassword": ["required", "min_length:8"],
    "ConfirmPassword": ["confirmed:WebPassword"]
})
```

### 2. Check for errors

```python
if errors:
    request.flash()
    return render_template("signup.html", errors=errors)
```

---

## 🔧 Writing Rules

### ✅ Required Rule

```python
@register_rule("required")
def required_rule(field, value):
    if value in (None, "", [], {}):
        return f"{field} is required"
```

### ✅ Regex Email Rule

```python
@register_rule("email")
def email_rule(field, value):
    import re
    if value and not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", str(value)):
        return f"{field} must be a valid email address"
```

### ✅ Parameterized Rule: `min_length:8`

```python
def min_length_rule(length):
    @register_rule(f"min_length:{length}")
    def rule(field, value):
        if value and len(str(value)) < length:
            return f"{field} must be at least {length} characters"
    return rule
```

### ✅ Cross-field: `confirmed:OtherField`

```python
def confirmed_rule(other_field):
    @register_rule(f"confirmed:{other_field}")
    def rule(field, value, all_data=None):
        if all_data and value != all_data.get(other_field):
            return f"{field} must match {other_field}"
    return rule
```

---

## 🔁 Inline Custom Rules

```python
def must_be_even(field, value):
    if value and int(value) % 2 != 0:
        return f"{field} must be an even number"

errors = request.validate({
    "LuckyNumber": ["required", must_be_even]
})
```

---

## 🧠 Advanced

### Dynamic Rule Retrieval

```python
get_rule("min_length:20")    # returns a callable rule
get_rule("confirmed:password")
```

---

## ✅ Rule Function Signature

```python
def rule(field: str, value: Any, all_data: dict = None) -> str | None:
    return "error message" or None
```

- `field`: the field name
- `value`: the value to validate
- `all_data`: optional dict of all fields for cross-comparisons

---

## 🧩 Integration Example

```python
from validators import required_rule, email_rule, min_length_rule

errors = request.validate({
    "username": ["required"],
    "email": ["required", "email"],
    "password": ["required", min_length_rule(8)]
})

if errors:
    flash("Please correct the errors.", "danger")
```

---

## 📜 License

MIT
