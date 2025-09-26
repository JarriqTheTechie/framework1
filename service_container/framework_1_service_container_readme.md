# Framework1 Service Container

A lightweight, Flask‑friendly service container with auto‑discovery, singletons, and decorator‑based dependency injection.

This README covers:

- What the container is and when to use it
- Manual registration and resolution
- Auto‑discovery with `init_container`
- Singletons via `@singleton` or explicit flags
- Function, method, and **Flask route** injection (`@injector`, `@injectable_route`)
- Patterns, best practices, and testing tips
- Edge cases & troubleshooting
- Minimal API reference

> Works standalone for manual resolution, and integrates tightly with Flask for injection (requires an app context when injecting).

---

## Installation & Requirements

- Python 3.10+
- Flask (for injection helpers; the container itself is framework‑agnostic)
- Your services should be importable Python classes (i.e., live in a package with `__init__.py`).

---

## Quick Start

### 1) Create and register services

```python
# lib/services/Mailer.py
class Mailer:
    def send(self, to: str, subject: str, body: str):
        print(f"→ Sending to {to}: {subject}\n{body}")
```

Manual registration:

```python
from framework1.service_container._ServiceContainer import ServiceContainer

container = ServiceContainer()
container.add('Mailer', Mailer)        # transient (new instance per resolution)
# container.add('Mailer', Mailer(), )  # OR prebuilt instance (see notes below)

mailer = container.get('Mailer')
mailer.send('user@example.com', 'Hello', 'Welcome aboard!')
```

> **Registration forms**
>
> - `container.add('ID', Class)` — stored as *service* (constructed each time `get` is called)
> - `container.add('ID', instance)` — works; `get` detects non‑callable and returns the instance
> - `container.add('ID', Class, singleton=True)` — *singleton* (constructed once and cached)

### 2) Auto‑discover user services (recommended)

```python
# app.py
from flask import Flask
from framework1.service_container._ServiceLoader import init_container

app = Flask(__name__)
init_container(app, services_path="lib/services")  # scans and registers classes as services/singletons
```

By default, `init_container`:

- Adds `app.container = ServiceContainer()`
- Scans `framework1/core_services/*.py` inside your venv and your `lib/services/*.py`
- Locates classes by module path and registers each under **its class name**
- Marks classes decorated with `@singleton` as singletons automatically

> **Package requirement**: your `lib` folder must be a package (have `__init__.py`) so classes are importable.

### 3) Inject services into Flask routes

```python
from framework1.service_container._Injector import injectable_route

# registers the route and injects dependencies by parameter annotation
@injectable_route(app, "/welcome", methods=["POST"])
def send_welcome(mailer: 'Mailer'):
    mailer.send("user@example.com", "Hello", "Welcome aboard!")
    return {"ok": True}
```

> The injector resolves parameter annotations. Use either the **class** (e.g., `mailer: Mailer`) or a **string name** matching the container ID (e.g., `mailer: 'Mailer'`).

---

## Deeper Dive

### Manual registration & resolution

```python
from framework1.service_container._ServiceContainer import ServiceContainer

c = ServiceContainer()

# 1) Transient service (constructed on each get)
c.add('ReportRepo', ReportRepo)
repo = c.get('ReportRepo')

# 2) Singleton service (constructed once)
c.add('Clock', Clock, singleton=True)
clock1 = c.get('Clock')
clock2 = c.get('Clock')
assert clock1 is clock2   # same instance

# 3) Prebuilt instance (no construction on get)
client = ThirdPartyClient(api_key="…")
c.add('Client', client)
same = c.get('Client')
assert same is client

# Existence checks
c.has('ReportRepo')          # services map
c.has_singleton('Clock')     # singletons map
```

**Notes**

- For non‑singletons registered as classes, `get('ID')` constructs a *new* instance each time.
- For prebuilt instances, `get('ID')` returns the same instance.
- For singletons registered with classes, the first `get` constructs and caches the instance internally.

### Auto‑discovery with `init_container`

```python
from framework1.service_container._ServiceLoader import init_container

# Typical Flask app factory setup

def create_app():
    app = Flask(__name__)
    # … configure app
    init_container(app, services_path="lib/services")
    return app
```

What it does:

- Creates a `ServiceContainer` and assigns it to `app.container`
- Loads classes from:
  - `…/site-packages/framework1/core_services/*.py` (virtualenv)
  - `os.getcwd()/lib/services/*.py` (your project)
- Resolves classes via import path (using `pydoc.locate`)
- Registers each class under its **class name** (`Class.__name__`)
- If a class has the attribute `__singleton__ = True` (set by `@singleton`), registers it as a singleton

> **Override order**: core services are registered first, then your `lib/services`. If a class name collides, **the last registration wins** (your project can override a core service by using the same class name).

### Marking singletons with `@singleton`

```python
from framework1.service_container._Injector import singleton

@singleton
class ViewProps:
    ...
```

When `init_container` sees `__singleton__` on a class, it registers it as a singleton automatically. Use this for stateless helpers or expensive one‑time constructs (connection pools, caches, etc.).

> You can also manually register singletons: `container.add('Clock', Clock, singleton=True)`.

### Function & method injection with `@injector`

```python
from framework1.service_container._Injector import injector
from flask import current_app

@injector
def send_weekly(mailer: 'Mailer', *, user_id: int):
    # app context is required for injection
    mailer.send("user@example.com", "Weekly Update", f"User: {user_id}")
    return {"ok": True}

# somewhere inside a request
with app.app_context():
    current_app.container.add('Mailer', Mailer)  # if not auto‑loaded
    send_weekly(user_id=42)  # mailer is injected
```

- The decorator inspects your function signature. For each **missing** `kwargs` value, it tries to resolve from `current_app.container` **by annotation**.
- If you decorate a **class method** and forget `self`, the injector attempts to instantiate the parent class and call the method correctly.

### Route injection with `@injectable_route`

This combines `app.route` and `@injector` into one decorator.

```python
from framework1.service_container._Injector import injectable_route

class ReportsController:
    @injectable_route(app, "/reports", methods=["GET"])  # auto registers + injects
    def index(self, repo: 'ReportRepo'):
        return {"total": repo.count_all()}
```

- The route is registered on the Flask `app`.
- Dependencies are injected into the route handler by **type annotation**.
- Works with plain functions or class methods (the wrapper will instantiate the parent class if needed).

### How the injector resolves dependencies

- If a parameter **annotation** is a class `MyService`, the container key used is `'MyService'`.
- If the annotation is a **string** `'my_custom_id'`, the container key is exactly that string.
- If a parameter already appears in `kwargs` (e.g., Flask provided it from the URL path), the injector **does not replace** it.
- Injection **requires** a Flask app context (`has_app_context()`), otherwise a `RuntimeError` is raised.

**Examples of annotation styles**

```python
# exact class name (container key will be 'Mailer')
def handler(mailer: Mailer): ...

# string ID (useful if you registered with a custom name or want to avoid imports)
def handler(mailer: 'mailer'): ...  # requires container.add('mailer', Mailer)
```

---

## Best Practices

1. **Prefer auto‑discovery + **``** for infrastructure services**

- Put your classes in `lib/services/` and mark true singletons with `@singleton`.
- Keep constructors fast and side‑effect‑free. Do not perform I/O in `__init__` if you can lazy‑load it in methods.

2. **Use explicit, unique class names**

- Container keys default to `Class.__name__`. If two classes share a name, the last registration wins.
- If you must register multiple implementations, register one or more under **string IDs** and annotate with those IDs.

3. **Design for injection**

- Do not reach into `current_app` inside service code. Accept collaborators as constructor args or method params.
- In Flask handlers, annotate dependencies and let the injector supply them.

4. **Keep services framework‑agnostic**

- Encapsulate third‑party SDKs and I/O behind services (e.g., `Mailer`, `Storage`, `Clock`). This makes swapping implementations trivial in tests.

5. **Testing**

- Build a fresh `ServiceContainer()` in tests or replace entries on `app.container`.
- For injection tests, push an app context: `with app.app_context(): …`.
- Swap real services with fakes: `app.container.add('Mailer', FakeMailer, singleton=True)`.

6. **Error handling & observability**

- When resolving fails, the injector raises a clear `ValueError` naming the missing service and parameter.
- Use `container.has('ID')` and `container.has_singleton('ID')` in startup diagnostics.

---

## Patterns & Recipes

### Config as a singleton

```python
from framework1.service_container._Injector import singleton

@singleton
class AppConfig:
    def __init__(self):
        self.smtp_host = "smtp.example.com"
        self.smtp_port = 587
```

Then:

```python
def handler(cfg: AppConfig, mailer: 'Mailer'):
    # cfg is the same instance for the lifetime of the app
    mailer.send("user@example.com", f"Using {cfg.smtp_host}", "…")
```

### Registering factories vs. instances

```python
# Factory (transient): new object each time
container.add('Uuid', lambda: uuid.uuid4())

# Instance (constant): same object every time
container.add('Now', datetime.utcnow())  # `get('Now')` returns the same value
```

> Internally, `get` tries to call services in the transient map. If that raises `TypeError` (not callable), it returns the object as‑is. This lets you register both factories and prebuilt instances.

### String IDs to avoid import cycles

```python
# registration
a  = ServiceContainer()
a.add('mailer', Mailer)  # custom id is lowercase

# injection
@injector
def some_fn(mailer: 'mailer'):  # annotate with the exact id string
    ...
```

### Controller methods without explicitly passing `self`

```python
class UsersController:
    @injectable_route(app, "/users", methods=["GET"])  # will instantiate UsersController for you
    def list(self, repo: 'UserRepo'):
        return repo.all()
```

The injector catches the classic "missing 1 required positional argument: 'self'" error and instantiates the parent class automatically.

---

## Edge Cases & Gotchas

- **App context required for injection**

  - `@injector` and `@injectable_route` rely on Flask app context. You’ll get `RuntimeError: No Flask app context available…` if you call such functions outside a request or `with app.app_context():` block.

- **Name mismatches**

  - Auto‑discovered classes are registered under their **class name**. If you annotate `'MyMailer'` but your class is `class Mailer:`, the resolver won’t find it.

- **Duplicate class names**

  - If two modules define `class Mailer`, the later registration wins. Prefer unique names or register one under a custom string ID.

- **Registering singletons as instances**

  - Singletons are designed to be registered as **classes** with `singleton=True` (or `@singleton`). If you instead register a prebuilt instance into the *singleton* map, it will be **called** on `get` and fail. Use the *services* map for instances (no `singleton=True`), or register the class as a singleton.

- **Silent **``** from **``

  - If an ID is missing, `container.get('X')` returns `None`. When using injection, the resolver raises a helpful error instead. Prefer `container.has()` checks in manual flows.

- **Service discovery requires importable modules**

  - `init_container` uses `pydoc.locate`. Your services must be in importable packages, e.g., `lib/services/Foo.py` with `lib/__init__.py` and `lib/services/__init__.py` present.

- **Windows vs POSIX paths**

  - The loader normalizes both `"/"` and `"\\"`, but malformed paths can still break discovery. Keep `services_path` simple (e.g., `lib/services`).

- **Constructor signatures**

  - The container calls `Class()` with **no arguments**. If your service requires constructor args, register a factory instead: `container.add('X', lambda: Class(arg))`.

---

## Minimal API Reference

### `ContainerInterface`

- `get(id)` → object | None — Return the entry for `id` (or `None` if missing)
- `has(id) -> bool` — Whether a transient service exists

### `ServiceContainer`

- `add(id, service, singleton=False)` — Register class, factory, or instance
- `get(id)` — Resolve transient or singleton
- `has(id) -> bool` — Is there a transient service for `id`?
- `has_singleton(id) -> bool` — Is there a singleton for `id`?

### `ServiceLoader`

- `init_container(app, services_path: str = "lib/services", debug=False)` — Build and populate `app.container` via auto‑discovery
- `to_class(path: str)` — Resolve a dotted path to a class (used internally)

### `Injector`

- `@injector` — Decorator to inject parameters by annotation (requires Flask app context)
- `@injectable_route(app, route, prefix=None, **options)` — Combines `app.route` and `@injector`
- `@singleton` — Decorator that marks a class with `__singleton__ = True` for auto‑discovery

---

## Troubleshooting

**“No Flask app context available…”**

- Ensure you are inside a request or wrap your call with `with app.app_context():`.

**“Cannot resolve service 'X' for parameter 'p' in 'f'.”**

- Check the annotation name matches the registered ID
- Confirm it is registered: `current_app.container.has('X')` or `.has_singleton('X')`
- For auto‑discovery, confirm the module is importable and the class name matches your annotation

**My route method says it’s missing **``

- Use `@injectable_route` on the method; it will instantiate the class automatically.

**Discovery doesn’t find my classes**

- Ensure `lib/services` is a real package (`__init__.py` present) and classes are at the top level of each file.

---

## Example Project Layout

```
project/
├─ app.py
├─ lib/
│  ├─ __init__.py
│  └─ services/
│     ├─ __init__.py
│     ├─ Mailer.py        # class Mailer
│     └─ AppConfig.py     # @singleton class AppConfig
└─ requirements.txt
```

---

## FAQ

**Q: Can I register the same ID twice?**\
Yes, the last registration wins. Prefer unique IDs or use string IDs to differentiate implementations.

**Q: Is the container thread‑safe?**\
No locking is performed. In typical Flask WSGI deployments it’s fine, but if you construct/replace services at runtime, do it during startup.

**Q: How do I pass constructor args?**\
Use a factory: `container.add('X', lambda: Class(arg1, arg2))`, or make a config singleton your services can read from.

**Q: Can I inject primitives (e.g., **``**)?**\
The injector only resolves registered services by **annotation name**. For request data, keep using Flask or your own parameter parsing.

---

## License

Part of the Framework1 toolkit. Use according to your project’s licensing terms.

