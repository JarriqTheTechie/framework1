import importlib
import importlib.util
import inspect
import json
import os
import sys
import pathlib
import subprocess
import time
from datetime import datetime

import click
import markupsafe
from dotenv import load_dotenv
from flask import Flask, redirect
from flask import g, request, render_template_string
from framework1.core_services.Request import Request
from jinja2 import FileSystemLoader

from .interfaces.LifecycleAware import LifecycleAware
from .service_container._Injector import injector, injectable_route
from .service_container._ServiceContainer import ServiceContainer
from .service_container._ServiceLoader import init_container


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
