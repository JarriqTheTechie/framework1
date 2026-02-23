import glob
import importlib
import importlib.util
import inspect
import json
import logging
import os
import pathlib
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlparse

import click
import markupsafe
from dotenv import load_dotenv
from flask import Flask
from flask import g, request, render_template_string
from jinja2 import FileSystemLoader

from framework1.core_services.Request import Request
from framework1.database.ActiveRecord import ActiveRecord
from framework1.utilities.DataKlass import DataKlass
from .interfaces.LifecycleAware import LifecycleAware
from .service_container._Injector import injector, injectable_route
from .service_container._ServiceContainer import ServiceContainer
from .service_container._ServiceLoader import init_container

_logger = logging.getLogger('framework1')


def all_subclasses(cls):
    subclasses = cls.__subclasses__()
    for subclass in subclasses:
        subclasses.extend(all_subclasses(subclass))
    return subclasses


def _is_truthy_env(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _profiler_enabled_in_request() -> bool:
    try:
        from flask import has_request_context
        if not has_request_context():
            return False
        return bool(getattr(g, "_framework1_profiler_enabled", False))
    except Exception:
        return False


def _profile_append_span(name: str, duration_ms: float, kind: str = "component"):
    if not _profiler_enabled_in_request():
        return
    spans = getattr(g, "_framework1_profile_spans", None)
    if spans is None:
        spans = []
        g._framework1_profile_spans = spans
    spans.append({
        "name": str(name),
        "kind": str(kind),
        "duration_ms": round(float(duration_ms), 2),
    })


@contextmanager
def profile_component(name: str, kind: str = "component"):
    """
    Lightweight per-request profiler span.
    Enabled automatically in debug mode or via FRAMEWORK1_ROUTE_PROFILER=true.
    """
    if not _profiler_enabled_in_request():
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        _profile_append_span(name=name, duration_ms=elapsed_ms, kind=kind)




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


def _normalize_roots(roots, default):
    """Ensures roots is a unique list while preserving order."""
    if not roots:
        roots = default
    if isinstance(roots, str):
        roots = [roots]
    seen = set()
    normalized = []
    for root in roots:
        if not root:
            continue
        path = root.replace("\\", "/")
        if path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def _expand_paths(patterns, default=None):
    """Expand glob patterns while staying backwards compatible with single paths."""
    normalized = _normalize_roots(patterns, [default] if default else [])
    expanded = []
    for pattern in normalized:
        matches = glob.glob(pattern)
        if matches:
            for m in matches:
                m_norm = m.replace("\\", "/")
                if m_norm not in expanded:
                    expanded.append(m_norm)
        else:
            if pattern and os.path.isdir(pattern):
                m_norm = pattern.replace("\\", "/")
                if m_norm not in expanded:
                    expanded.append(m_norm)
    return expanded


def _configure_template_loader(app: Flask, template_roots):
    """
    Compose a ChoiceLoader so domain UI templates can co-exist with legacy handlers.
    Falls back to the default FileSystemLoader when no extra roots are provided.
    """
    if not template_roots:
        return None

    from jinja2 import ChoiceLoader, FileSystemLoader

    existing_loader = app.jinja_loader
    domain_loader = FileSystemLoader(template_roots)

    if isinstance(existing_loader, ChoiceLoader):
        loaders = [domain_loader] + list(existing_loader.loaders)
    elif existing_loader:
        loaders = [domain_loader, existing_loader]
    else:
        loaders = [domain_loader]

    app.jinja_loader = ChoiceLoader(loaders)
    return app.jinja_loader


def _apply_jinja_extensions(app: Flask, extensions):
    if not extensions:
        return
    for ext in extensions:
        try:
            app.jinja_env.add_extension(ext)
        except Exception:
            # keep silent to avoid breaking apps; mirrors existing tolerant behavior
            if app.debug:
                app.logger.debug(f"[Framework1] Failed to add Jinja extension {ext}")


def _apply_network_routing_config(app: Flask, **kwargs):
    """
    Apply optional Flask host/subdomain routing settings in one place.
    Supports explicit kwargs first, then environment fallbacks.
    """
    server_name = kwargs.get("server_name") or os.getenv("FRAMEWORK1_SERVER_NAME") or os.getenv("SERVER_NAME")
    preferred_url_scheme = kwargs.get("preferred_url_scheme") or os.getenv("FRAMEWORK1_PREFERRED_URL_SCHEME")
    session_cookie_domain = kwargs.get("session_cookie_domain") or os.getenv("FRAMEWORK1_SESSION_COOKIE_DOMAIN")

    subdomain_matching = kwargs.get("subdomain_matching")
    if subdomain_matching is None:
        env_subdomain_matching = os.getenv("FRAMEWORK1_SUBDOMAIN_MATCHING")
        if env_subdomain_matching is not None:
            subdomain_matching = _is_truthy_env(env_subdomain_matching)

    if server_name:
        app.config["SERVER_NAME"] = server_name
    if preferred_url_scheme:
        app.config["PREFERRED_URL_SCHEME"] = preferred_url_scheme
    if session_cookie_domain:
        app.config["SESSION_COOKIE_DOMAIN"] = session_cookie_domain
    if subdomain_matching is not None:
        app.subdomain_matching = bool(subdomain_matching)


def _apply_cookie_security_config(app: Flask, **kwargs):
    """
    Apply secure-by-default cookie settings with sensible localhost behavior.
    """
    cookie_samesite = kwargs.get("session_cookie_samesite") or os.getenv("FRAMEWORK1_SESSION_COOKIE_SAMESITE")
    cookie_secure = kwargs.get("session_cookie_secure")
    if cookie_secure is None:
        env_secure = os.getenv("FRAMEWORK1_SESSION_COOKIE_SECURE")
        if env_secure is not None:
            cookie_secure = _is_truthy_env(env_secure)

    if cookie_samesite:
        app.config["SESSION_COOKIE_SAMESITE"] = str(cookie_samesite).strip()
    else:
        app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    if cookie_secure is not None:
        app.config["SESSION_COOKIE_SECURE"] = bool(cookie_secure)
    else:
        app.config.setdefault("SESSION_COOKIE_SECURE", False)

    server_name = str(app.config.get("SERVER_NAME", "") or "").split(":")[0].strip().lower()
    session_cookie_domain = app.config.get("SESSION_COOKIE_DOMAIN")
    if session_cookie_domain and server_name in {"localhost", "127.0.0.1"}:
        # Browsers can behave inconsistently with explicit localhost cookie domains.
        app.config.pop("SESSION_COOKIE_DOMAIN", None)

    # Keep host-only cookies by default for localhost if explicit domain is not provided.
    if not app.config.get("SESSION_COOKIE_DOMAIN") and server_name in {"localhost", "127.0.0.1"}:
        app.config["SESSION_COOKIE_DOMAIN"] = None


def _apply_proxy_fix(app: Flask, **kwargs):
    trust_proxy = kwargs.get("trust_proxy")
    if trust_proxy is None:
        trust_proxy = _is_truthy_env(os.getenv("FRAMEWORK1_TRUST_PROXY"))
    if not trust_proxy:
        return

    x_for = int(os.getenv("FRAMEWORK1_PROXY_X_FOR", kwargs.get("proxy_x_for", 1)))
    x_proto = int(os.getenv("FRAMEWORK1_PROXY_X_PROTO", kwargs.get("proxy_x_proto", 1)))
    x_host = int(os.getenv("FRAMEWORK1_PROXY_X_HOST", kwargs.get("proxy_x_host", 1)))
    x_port = int(os.getenv("FRAMEWORK1_PROXY_X_PORT", kwargs.get("proxy_x_port", 1)))
    x_prefix = int(os.getenv("FRAMEWORK1_PROXY_X_PREFIX", kwargs.get("proxy_x_prefix", 1)))

    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=x_for,
        x_proto=x_proto,
        x_host=x_host,
        x_port=x_port,
        x_prefix=x_prefix,
    )


def _csrf_exempt_paths() -> set[str]:
    raw = str(os.getenv("FRAMEWORK1_CSRF_EXEMPT_PATHS", "") or "").strip()
    paths = set()
    if not raw:
        return paths
    for p in raw.split(","):
        cleaned = str(p).strip()
        if cleaned:
            paths.add(cleaned)
    return paths


def _same_origin_host_check() -> bool:
    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    host = str(request.host or "").strip().lower()
    if not host:
        return False

    if origin:
        parsed = urlparse(origin)
        origin_host = str(parsed.netloc or "").strip().lower()
        if origin_host and origin_host != host:
            return False

    if referer:
        parsed = urlparse(referer)
        referer_host = str(parsed.netloc or "").strip().lower()
        if referer_host and referer_host != host:
            return False

    return True


def _discover_handler_module_paths(handler_roots=None):
    """Yield importable module paths for Python files under handler roots."""
    roots = _expand_paths(handler_roots, "lib/handlers")
    seen = set()

    for handlers_dir in roots:
        handlers_path = pathlib.Path(handlers_dir)
        if not handlers_path.is_dir():
            continue
        for file in handlers_path.rglob("*.py"):
            if file.name == "__init__.py":
                continue
            try:
                relative_path = file.with_suffix("").relative_to(pathlib.Path("."))
            except ValueError:
                # Skip non-project-local paths; existing behavior is focused on project handlers.
                continue
            module_path = ".".join(relative_path.parts)
            if module_path in seen:
                continue
            seen.add(module_path)
            yield module_path


def discover_handlers(debug=False, handler_roots=None):
    loaded_modules = []
    for module_path in _discover_handler_module_paths(handler_roots=handler_roots):
        try:
            loaded_modules.append(importlib.import_module(module_path))
        except Exception as e:
            if debug:
                _logger.debug(f"Error loading handler {module_path}: {e}")
                raise e
    return loaded_modules


def discover_and_init_controllers(debug=False, controller_roots=None, preloaded_modules=None):
    """Discovers controller classes and initializes them."""
    controllers = []
    modules = preloaded_modules if preloaded_modules is not None else discover_handlers(
        debug=debug,
        handler_roots=controller_roots
    )

    for module in modules:
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                name.endswith("Controller")
                and obj.__module__ == module.__name__
            ):
                try:
                    instance = obj()
                    controllers.append(instance)
                    if debug:
                        _logger.debug(f"Initialized controller: {name}")
                except Exception as e:
                    if debug:
                        _logger.debug(f"Failed to initialize controller {name}: {str(e)}")

    return controllers


def discover_convention_routes(app, debug=False, handler_roots=None):
    for module_path in _discover_handler_module_paths(handler_roots=handler_roots):
        try:
            mod = importlib.import_module(module_path)
            view_func = getattr(mod, "view", None)

            if not callable(view_func):
                continue

            # Route path: from module-level 'route' or path
            route_path = getattr(mod, "route", None)
            if not route_path:
                parts = module_path.split(".")[2:]  # skip lib, handlers
                route_path = "/" + "/".join(parts)

            # HTTP methods: from module-level 'methods' or default to ["GET"]
            methods = getattr(mod, "methods", ["GET"])

            app.route(route_path, methods=methods)(injector(view_func))
            if debug:
                app.logger.debug(f"[Router] Registered {module_path}.view -> {route_path} [{', '.join(methods)}]")

        except Exception as e:
            if debug:
                app.logger.debug(f"[Router] Error loading {module_path}: {e}")


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
                                app.logger.debug(f"Controller {controller.__class__.__name__} returned non-list navigation items.")
                    except Exception as e:
                        if debug:
                            app.logger.debug(f"Error in GetNavigation for {controller.__class__.__name__}: {e}")

    # Sort menu items by weight
    menu_items.sort(key=lambda x: x.get('weight', 100))
    return menu_items


def _current_request_subdomain(app: Flask) -> str | None:
    host = str(request.host or "").split(":")[0].strip().lower()
    server_name = str(app.config.get("SERVER_NAME", "") or "").split(":")[0].strip().lower()
    if not host or not server_name:
        return None
    if host == server_name:
        return None
    suffix = f".{server_name}"
    if not host.endswith(suffix):
        return None
    subdomain = host[: -len(suffix)].strip(".")
    return subdomain or None


def _nav_item_allowed_subdomains(item: dict) -> list[str | None] | None:
    raw = item.get("subdomains")
    if raw is None and "subdomain" in item:
        raw = item.get("subdomain")
    if raw is None:
        return None

    if isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = [raw]

    normalized: list[str | None] = []
    for value in values:
        if value is None:
            normalized.append(None)
            continue
        cleaned = str(value).strip()
        if not cleaned:
            normalized.append(None)
            continue
        normalized.append(cleaned)
    return normalized


def _is_nav_item_visible_for_request(app: Flask, item: dict) -> bool:
    visible = item.get("visible", True)
    if callable(visible):
        try:
            visible = visible()
        except Exception:
            visible = False
    if not bool(visible):
        return False

    allowed_subdomains = _nav_item_allowed_subdomains(item)
    if allowed_subdomains is None:
        return _current_request_subdomain(app) is None

    current_subdomain = _current_request_subdomain(app)
    normalized_allowed = []
    for value in allowed_subdomains:
        if value == "<subdomain>":
            normalized_allowed.append(current_subdomain if current_subdomain else "<subdomain>")
        else:
            normalized_allowed.append(value)
    return current_subdomain in normalized_allowed


def _navigation_items_for_request(app: Flask, debug=False) -> list[dict]:
    menu_items = []
    for controller in app.controllers:
        if hasattr(controller, "GetNavigation"):
            try:
                items = controller.GetNavigation()
                if isinstance(items, list):
                    menu_items.extend(items)
                elif debug:
                    app.logger.debug(
                        f"Controller {controller.__class__.__name__} returned non-list navigation items."
                    )
            except Exception as e:
                if debug:
                    app.logger.debug(f"Error in GetNavigation for {controller.__class__.__name__}: {e}")

    filtered = [item for item in menu_items if _is_nav_item_visible_for_request(app, item)]
    filtered.sort(key=lambda x: x.get("weight", 100))
    return filtered


def Framework1(app: Flask, debug=False, **kwargs):
    load_dotenv()
    app.secret_key = os.getenv('APP_SECRET_KEY')
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 60 * 60 * 24 * 30  # 30 days
    _apply_network_routing_config(app, **kwargs)
    _apply_cookie_security_config(app, **kwargs)
    _apply_proxy_fix(app, **kwargs)
    debug_logging_env = kwargs.get("debug_logging_env", "ORM_DEBUG")
    if debug_logging_env and os.getenv(debug_logging_env, "false").lower() == "true":
        app.logger.setLevel(logging.INFO)

    # Optional knobs (all backwards compatible)
    controller_roots = kwargs.get("controller_roots")
    template_roots = kwargs.get("template_roots")
    jinja_extensions = kwargs.get("jinja_extensions")
    service_roots = kwargs.get("service_roots")
    event_roots = kwargs.get("event_roots")

    """Initializes the Flask application with service containers, dynamic module imports,
    and template/static configurations.
    """
    # Initialize service container
    services_path_kwarg = kwargs.get("services_path")
    if services_path_kwarg:
        service_paths = _normalize_roots(services_path_kwarg, [])
    else:
        service_paths = _expand_paths(service_roots, "lib/services")
        if event_roots:
            service_paths += _expand_paths(event_roots, None)
    service_paths = _normalize_roots(service_paths, service_paths)
    init_container(app, services_path=";".join(service_paths), debug=debug)
    app._framework1_lifecycle_singletons = []
    for name in app.container._singletons.keys():
        instance = app.container.get(name)
        if isinstance(instance, LifecycleAware):
            app._framework1_lifecycle_singletons.append(instance)

    handler_modules = discover_handlers(debug=debug, handler_roots=controller_roots)
    controllers = discover_and_init_controllers(
        debug=debug,
        controller_roots=controller_roots,
        preloaded_modules=handler_modules
    )
    app.controllers = controllers
    app.menu_items = collect_navigation_items(app, debug)

    # discover_convention_routes(app)

    # Set Jinja template and static file locations
    app.jinja_loader = FileSystemLoader("lib/handlers")
    _configure_template_loader(app, _expand_paths(template_roots, None))
    _apply_jinja_extensions(app, jinja_extensions)
    app.static_folder = os.path.join(os.getcwd(), "lib/resources")

    # app.static_url_path = '/resources'




    @app.before_request
    def _framework1_before_request():
        g._framework1_lifecycle_services = []
        g._framework1_request_started_at = time.perf_counter()
        profiler_enabled = bool(debug) or _is_truthy_env(os.getenv("FRAMEWORK1_ROUTE_PROFILER"))
        g._framework1_profiler_enabled = profiler_enabled
        if profiler_enabled:
            g._framework1_profile_request_started_at = time.perf_counter()
            g._framework1_profile_spans = []

        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path not in _csrf_exempt_paths():
            if not _same_origin_host_check():
                return {"success": False, "message": "Cross-origin request blocked"}, 403

        skip = request.path.startswith("/static") or request.method not in ("GET", "POST") or request.path.startswith(
            "/resources")
        if skip:
            return

        lifecycle_services = app._framework1_lifecycle_singletons
        g._framework1_lifecycle_services = lifecycle_services
        start_ctx = {
            "path": request.path,
            "method": request.method,
            "headers": dict(request.headers),
        }

        for instance in lifecycle_services:
            instance.on_request_start(start_ctx)

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

        if getattr(g, "_framework1_profiler_enabled", False):
            started_at = g.get("_framework1_profile_request_started_at", time.perf_counter())
            total_ms = (time.perf_counter() - started_at) * 1000.0
            endpoint_name = request.endpoint or "<unknown>"
            _profile_append_span(name=f"controller:{endpoint_name}", duration_ms=total_ms, kind="controller")
            spans = g.get("_framework1_profile_spans", [])
            spans_sorted = sorted(spans, key=lambda x: x.get("duration_ms", 0.0), reverse=True)
            top = spans_sorted[:5]
            top_summary = "; ".join(f'{s["name"]}:{s["duration_ms"]:.2f}' for s in top)

            response.headers["X-F1-Profile-Total-Ms"] = f"{total_ms:.2f}"
            response.headers["X-F1-Profile-Spans"] = str(len(spans))
            if top_summary:
                response.headers["X-F1-Profile-Top"] = top_summary[:512]

            if debug:
                app.logger.info(
                    "[F1-Profile] method=%s path=%s endpoint=%s status=%s total_ms=%.2f top=%s",
                    request.method,
                    request.path,
                    request.endpoint,
                    response.status_code,
                    total_ms,
                    top,
                )

        # Save status for teardown tracking
        g._framework1_response_status = response.status_code
        return response


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
            'navigation': _navigation_items_for_request(app, debug)
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

