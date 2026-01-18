import importlib
import importlib.util
import inspect
import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime
from typing import TypedDict, Any
from flask import current_app, template_rendered

import click
import markupsafe
from blinker import Namespace
from dotenv import load_dotenv
from flask import Flask
from flask import g, request, render_template_string, has_app_context
from framework1.core_services.Request import Request
from framework1.database.ActiveRecord import ActiveRecord
from framework1.utilities.DataKlass import DataKlass
from jinja2 import FileSystemLoader

from .interfaces.LifecycleAware import LifecycleAware
from .service_container._Injector import injector, injectable_route
from .service_container._ServiceContainer import ServiceContainer
from .service_container._ServiceLoader import init_container

my_signals = Namespace()
model_loaded = my_signals.signal('model_loaded')

from collections import defaultdict


# Define your singleton class
class SingletonObject:
    def __init__(self):
        self.data = None
        self.queries = []


# Create a function to get or create the singleton object
def get_singleton_object():
    if not has_app_context():
        raise RuntimeError("Not in app context")

    if not hasattr(g, 'singleton_object'):
        g.singleton_object = SingletonObject()
    return g.singleton_object


def hydrated(self):
    print("Hydrated model:", self.__class__.__name__)
    model_loaded.send(self)


def all_subclasses(cls):
    subclasses = cls.__subclasses__()
    for subclass in subclasses:
        subclasses.extend(all_subclasses(subclass))
    return subclasses


class ModelCollectorState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.start_time = time.perf_counter()
        self.models_processed = 0
        self.items_collected = 0
        self.bytes_collected = 0
        self.warnings = []
        self.raw_dump = []

    def add_item(self, model_name, data):
        self.models_processed += 1
        self.items_collected += 1
        self.bytes_collected += sys.getsizeof(data)

        # store for debugging (optional)
        self.raw_dump.append(
            {"model": model_name, "data": data}
        )

    @property
    def elapsed_ms(self):
        return round((time.perf_counter() - self.start_time) * 1000, 2)

    @property
    def memory_kb(self):
        return round(self.bytes_collected * 0.0009765625, 2)


def get_collector_state():
    if not hasattr(g, "collector_state"):
        g.collector_state = ModelCollectorState()
    return g.collector_state


class ModelCollector(dict):
    """
    Lightweight container for collected model data.
    Always stores: model (string), data (list), count (int)
    """

    def __init__(self, model: str, data: list):
        super().__init__(
            model=model,
            data=data,
            count=len(data)
        )


def pass_model_to_g(model):
    if not has_app_context():
        return False

    state = get_collector_state()
    model_name = model.__class__.__name__

    fields = model.__class__.get_fields()
    data = {
        k: v for k, v in model.__data__.items()
        if k in fields and v is not None
    }

    # record performance event
    state.add_item(model_name, data)

    if not hasattr(g, "models"):
        g.models = [ModelCollector(model_name, [data])]
        return True

    for item in g.models:
        if item["model"] == model_name:
            item["data"].append(data)
            item["count"] = len(item["data"])
            return True

    g.models.append(ModelCollector(model_name, [data]))
    return True


def debug_collector():
    state = get_collector_state()

    print("\n=== MODEL COLLECTION DEBUG ===")
    print(f"Models processed:   {state.models_processed}")
    print(f"Items collected:    {state.items_collected}")
    print(f"Memory collected:   {state.memory_kb} kb")
    print(f"Time elapsed:       {state.elapsed_ms} ms")

    if state.warnings:
        print("\nWarnings:")
        for w in state.warnings:
            print(" -", w)

    print("\nRaw collected items:")
    pprint.pprint(state.raw_dump)


def reset_collector():
    state = get_collector_state()
    state.reset()
    if hasattr(g, "models"):
        del g.models
    if hasattr(g, "model_debug"):
        del g.model_debug


def render_template_string_safe_internal(relative_path, **context):
    """Renders a template from a string, ensuring the path is safe."""
    venv_path = sys.prefix + "/Lib/site-packages/framework1/templates"
    relative_path = os.path.join(venv_path, relative_path)

    if not os.path.exists(relative_path):
        raise FileNotFoundError(f"Template file {relative_path} does not exist.")

    with open(relative_path, 'r', encoding='utf-8') as file:
        template_content = file.read()

    return render_template_string(template_content, **context)


def render_template_string_safe_external(relative_path, **context):
    """Renders a template from a string, ensuring the path is safe."""
    handlers_path = os.getenv("HANDLERS_PATH", "lib/handlers")
    relative_path = os.path.join(os.getcwd(), handlers_path, relative_path)

    if not os.path.exists(relative_path):
        raise FileNotFoundError(f"Template file {relative_path} does not exist.")

    with open(relative_path, 'r', encoding='utf-8') as file:
        template_content = file.read()

    return render_template_string(template_content, **context)


def discover_and_init_controllers(debug=False):
    """Discovers all controller classes in lib/handlers and initializes them"""
    controllers = []
    handlers_dir = "lib/handlers"

    # Walk through all directories in handlers
    for root, dirs, files in os.walk(handlers_dir):
        for file in files:
            if file.endswith("Controller.py"):
                # Convert file path to module path
                module_path = os.path.join(root, file).replace("/", ".").replace("\\", ".")[:-3]
                try:
                    # Import the module
                    module = importlib.import_module(module_path)

                    # Find controller class in the module
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) and
                                name.endswith('Controller') and
                                obj.__module__ == module_path):
                            try:
                                # Initialize the controller
                                instance = obj()
                                controllers.append(instance)
                                if debug:
                                    print(f"Initialized controller: {name}")
                            except Exception as e:
                                if debug:
                                    print(f"Failed to initialize controller {name}: {str(e)}")
                except Exception as e:
                    if debug:
                        print(f"Failed to import controller module {module_path}: {str(e)}")

    return controllers


def discover_handlers(debug=False):
    handlers_dir = pathlib.Path("lib/handlers")
    for file in handlers_dir.rglob("*.py"):
        if file.name == "__init__.py":
            continue

        # Convert to dotted module path (e.g., lib.handlers.dashboard)
        relative_path = file.with_suffix('').relative_to(pathlib.Path('.'))
        module_path = '.'.join(relative_path.parts)

        try:
            importlib.import_module(module_path)
        except Exception as e:
            if debug:
                print(f"Error loading handler {module_path}: {e}")
                raise e


def discover_convention_routes(app, debug=False):
    handlers_dir = pathlib.Path("lib/handlers")
    for file in handlers_dir.rglob("*.py"):
        if file.name == "__init__.py":
            continue

        relative_path = file.with_suffix('').relative_to(pathlib.Path('.'))
        module_path = '.'.join(relative_path.parts)

        try:
            mod = importlib.import_module(module_path)
            view_func = getattr(mod, "view", None)

            if not callable(view_func):
                continue

            # Route path: from module-level 'route' or path
            route_path = getattr(mod, "route", None)
            if not route_path:
                parts = relative_path.parts[2:]  # skip lib, handlers
                route_path = "/" + "/".join(parts)

            # HTTP methods: from module-level 'methods' or default to ["GET"]
            methods = getattr(mod, "methods", ["GET"])

            app.route(route_path, methods=methods)(injector(view_func))
            if debug:
                print(f"[Router] Registered {module_path}.view → {route_path} [{', '.join(methods)}]")

        except Exception as e:
            if debug:
                print(f"[Router] Error loading {module_path}: {e}")


def collect_navigation_items(app: Flask, debug=False):
    """Collect navigation items from all controllers within app context"""
    menu_items = []
    with app.app_context():
        with app.test_request_context():  # This provides request context for url_for
            for controller in app.controllers:
                if hasattr(controller, "GetNavigation"):
                    try:
                        items = controller.GetNavigation()
                        if isinstance(items, list):
                            menu_items.extend(items)
                        else:
                            if debug:
                                print(f"Controller {controller.__class__.__name__} returned non-list navigation items.")
                    except Exception as e:
                        if debug:
                            print(f"Error in GetNavigation for {controller.__class__.__name__}: {e}")

    # Sort menu items by weight
    menu_items.sort(key=lambda x: x.get('weight', 100))
    return menu_items


def Framework1(app: Flask, debug=False, **kwargs):
    load_dotenv()
    app.secret_key = os.getenv('APP_SECRET_KEY')
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 60 * 60 * 24 * 30  # 30 days

    """Initializes the Flask application with service containers, dynamic module imports,
    and template/static configurations.
    """
    # Initialize service container
    init_container(app, services_path=kwargs.get("services_path", "lib/services"), debug=debug)
    discover_handlers(debug)
    controllers = discover_and_init_controllers(debug)
    app.controllers = controllers
    app.menu_items = collect_navigation_items(app, debug)

    # discover_convention_routes(app)

    # Set Jinja template and static file locations
    app.jinja_loader = FileSystemLoader("lib/handlers")
    app.static_folder = os.path.join(os.getcwd(), "lib/resources")

    # app.static_url_path = '/resources'

    model_loaded.connect(pass_model_to_g)
    models = all_subclasses(ActiveRecord)
    for model in models:
        model.on("retrieved", hydrated)

    @app.before_request
    def init_model_collection():
        g.models = []
        g.collector_state = ModelCollectorState()
        g.model_debug = {
            "models_processed": 0,
            "items_collected": 0,
            "memory_collected": "0 kb",
            "collection_time": "0 ms",
            "warnings": [],
            "grouped_summary": []
        }

    @app.before_request
    def _framework1_before_request():
        g._framework1_lifecycle_services = []
        g._framework1_request_started_at = time.perf_counter()

        skip = request.path.startswith("/static") or request.method not in ("GET", "POST") or request.path.startswith(
            "/resources")
        if skip:
            return

        for name, cls in app.container._singletons.items():
            instance = app.container.get(name)
            if isinstance(instance, LifecycleAware):
                instance.on_request_start({
                    "path": request.path,
                    "method": request.method,
                    "headers": dict(request.headers),
                })
                g._framework1_lifecycle_services.append(instance)

    @app.teardown_request
    def _framework1_teardown_request(exception=None):
        duration = round(time.perf_counter() - g.get("_framework1_request_started_at", 0), 4)

        ctx = {
            "exception": exception,
            "path": request.path,
            "method": request.method,
            "duration": duration,
            "status": getattr(g, "_framework1_response_status", None)
        }

        for instance in g.get("_framework1_lifecycle_services", []):
            if exception and hasattr(instance, "on_request_exception"):
                instance.on_request_exception(ctx)

            if hasattr(instance, "on_request_end"):
                instance.on_request_end(ctx)

    @app.after_request
    def _framework1_after_request(response):
        ctx = {
            "path": request.path,
            "method": request.method,
            "status": response.status_code,
            "content_length": response.calculate_content_length()
        }

        for instance in g.get("_framework1_lifecycle_services", []):
            if hasattr(instance, "on_response_sent"):
                instance.on_response_sent(ctx)

        # Save status for teardown tracking
        g._framework1_response_status = response.status_code
        return response

    @app.get('/app/save-state')
    def saveState():
        from lib.models.ViewState import ViewState
        view_props = app.container.get('ViewProps')
        request: Request = app.container.get('Request')
        state = request.headers("Hx-Current-Url")
        name = request.headers("Hx-Prompt")

        ViewState().create(**{
            "name": name,
            "url": state,
            "is_global": 0,
            "belongs_to": None
        })
        return ""

    @app.template_global()
    def view_state():
        from lib.models.ViewState import ViewState
        return ViewState()

    # Expose environment variables to templates
    @app.template_global("env")
    def env(key):
        return os.getenv(key)

    @app.template_filter("humanize_dt")
    def humanize_dt(value):
        """Converts a datetime string into a human-readable format."""
        date_formats = [
            "%Y-%m-%d %H:%M:%S.%f",  # Standard format with microseconds
            "%Y-%m-%d %H:%M:%S.%f%z"  # Format with timezone
        ]

        date_time_obj = None
        for fmt in date_formats:
            try:
                date_time_obj = datetime.strptime(value, fmt)
                break  # Stop at the first successful parse
            except ValueError:
                continue  # Try the next format

        if not date_time_obj:
            return value  # Return the original value if parsing fails

        return date_time_obj.strftime("%A, %B %d, %Y at %I:%M %p")

    @app.template_filter("split")
    def split(value, sep, index):
        return value.split(sep)[index]

    @app.template_global("is_active")
    def is_active(current_route):
        if current_route in str(request.query_string):
            return "active"
        return ""

    @app.template_global("current_path")
    def current_path():
        return request.path

    @app.template_global("url")
    def url():
        return request.url

    @app.template_filter("safe_iter")
    def safe_iter(s):
        if not s:
            return []
        if type(s) == list:
            return s
        return [s]

    @app.template_filter("json_load")
    def json_load(value):
        """Converts a JSON string into a Python object."""
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value  # Return the original value if parsing fails

    @app.template_filter("asdict")
    def asdict_filter(val):
        if isinstance(val, list):
            return [v.to_dict() if isinstance(v, DataKlass) else v for v in val]
        if isinstance(val, DataKlass):
            return val.to_dict()
        return val

    @app.template_filter("PageTitle")
    def page_title(value):
        return markupsafe.Markup(
            f"""
                <h5 class="fw-bold mb-4">
                    <span style="border-bottom: 5px solid #9300ff !important;">
                        {value}
                    </span>

                </h5>
            """
        )

    @app.context_processor
    def inject_navigation():
        return {
            'navigation': app.menu_items
        }

    @app.cli.command("manage")
    @click.argument('args', nargs=-1)
    def manage(args):
        import sys
        venv_path = f"{sys.prefix}/Lib/site-packages/framework1"
        manage_path = os.path.join(venv_path, 'manage.py')
        if not os.path.exists(manage_path):
            click.echo(f"Error: Could not find manage.py at {manage_path}", err=True)
            sys.exit(1)

        try:
            result = subprocess.run(
                [sys.executable, manage_path] + list(args),
                check=True
            )
            sys.exit(result.returncode)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)

    return app
