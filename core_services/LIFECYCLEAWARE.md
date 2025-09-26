# Framework1

**Framework1** is a lightweight Flask extension that provides:

- ✅ Convention-based route discovery
- ✅ A robust dependency injection system
- ✅ Lifecycle-aware services (middleware-style hooks)
- ✅ Clean template and static asset organization
- ✅ Developer-friendly conventions for modular architecture

---

## 🚀 Features

### 🪄 Convention-Based Routing

Framework1 auto-discovers view modules inside `lib/handlers/**` and registers routes based on:
- Module path (e.g., `lib/handlers/users/profile.py` → `/users/profile`)
- Optional `route` and `methods` variables

#### 🔧 Example Handler

```python
# lib/handlers/users/profile.py

route = "/users/<int:user_id>"
methods = ["GET"]

def view(user_service: UserService, user_id: int):
    user = user_service.get_user(user_id)
    return f"Welcome, {user.name}"
```

---

### 🧠 Dependency Injection via Service Container

Framework1 auto-injects services into view functions based on type hints.

#### ✅ Example Service

```python
from framework1.service_container._Injector import singleton

@singleton
class UserService:
    def get_user(self, user_id):
        ...
```

#### ✅ Injected View

```python
def view(user_service: UserService, user_id: int):
    ...
```

---

### 📈 Lifecycle-Aware Services

Any singleton service that implements the `LifecycleAware` interface will automatically receive:

| Hook | Trigger |
|------|---------|
| `on_request_start(context)` | Before each request |
| `on_request_exception(context)` | If an exception occurs |
| `on_request_end(context)` | Always after request completes |
| `on_response_sent(context)` | After response is sent to client |

#### ✅ Example

```python
from framework1.core_services.LifecycleAware import LifecycleAware

class RequestLogger(LifecycleAware):
    def on_request_start(self, ctx):
        print(f"Started: {ctx['method']} {ctx['path']}")

    def on_request_end(self, ctx):
        print(f"Ended: {ctx['method']} in {ctx['duration']}s")
```

---

## 🧱 Project Structure

```
lib/
├── handlers/
│   ├── __init__.py
│   └── users/
│       └── profile.py
├── services/
│   └── UserService.py
framework1/
├── __init__.py
├── service_container/
│   ├── _ServiceContainer.py
│   ├── _Injector.py
│   └── _ServiceLoader.py
├── interfaces/
│   └── LifecycleAware.py
```

---

## 🧪 Example App Initialization

```python
from flask import Flask
from framework1 import Framework1

def create_app():
    app = Flask(__name__)
    Framework1(app)
    return app
```

Then run with:

```bash
FLASK_APP=main:create_app
FLASK_ENV=development
flask run
```

---

## 📦 Template Filters and Globals

Framework1 adds custom filters and globals for cleaner Jinja templates:

- `humanize_dt(value)` – Formats datetime strings
- `split(value, sep, index)` – String splitting
- `safe_iter(value)` – Wraps non-list into list
- `json_load(value)` – Parses JSON strings
- `env(key)` – Access environment variables
- `current_path()` – Returns current request path
- `is_active(route_fragment)` – Adds `"active"` CSS class if route matches

---

## 🤝 License

MIT
