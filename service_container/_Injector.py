import importlib
import inspect
import os
import sys
from functools import wraps
from flask import current_app, has_app_context


def get_parent_class(func):
    if not callable(func):
        return None

    qualname = func.__qualname__  # e.g., 'MyClass.my_method'
    if '.' not in qualname:
        return None  # not a method

    parent_name = qualname.rsplit('.', 1)[0]

    # Get the module where the function is defined
    module = sys.modules.get(func.__module__)
    if not module:
        return None

    # Traverse attributes in the module to find a matching class
    for obj_name in dir(module):
        obj = getattr(module, obj_name)
        if inspect.isclass(obj) and obj.__name__ == parent_name:
            return obj

    return None


def _service_name_for_param(param: inspect.Parameter):
    if param.annotation is inspect.Parameter.empty:
        return None
    return param.annotation if isinstance(param.annotation, str) else getattr(param.annotation, "__name__", None)


def service_resolver(service_name: str | None, param_name: str, func_name: str):
    """Resolves and retrieves the appropriate service from the container."""
    if not has_app_context():
        raise RuntimeError(f"No Flask app context available for injecting '{param_name}' in '{func_name}'")

    if not service_name:
        return None

    container = current_app.container
    if not (container.has(service_name) or container.has_singleton(service_name)):
        raise ValueError(
            f"[Injector] Cannot resolve service '{service_name}' for parameter '{param_name}' in '{func_name}'. "
            f"Ensure it is registered in the container."
        )

    return container.get(service_name)


def injector(func):
    sig = inspect.signature(func)
    needs_self = "self" in sig.parameters
    parent_class_hint = get_parent_class(func) if needs_self else None
    injectable_params = [
        (name, _service_name_for_param(param))
        for name, param in sig.parameters.items()
        if name != "self"
    ]

    @wraps(func)
    def wrapper(*args, **kwargs):
        parent_class = parent_class_hint

        # Pre-instantiate controller methods so we never miss 'self'
        if needs_self and "self" not in kwargs and not args:
            if parent_class is None:
                parent_class = get_parent_class(func)
            if parent_class:
                args = (parent_class(), *args)

        for name, service_name in injectable_params:
            if name in kwargs:  # already provided by Flask (e.g. user_id)
                continue
            service = service_resolver(service_name, name, func.__name__)
            if service is not None:
                kwargs[name] = service
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "missing 1 required positional argument: 'self'" in str(e):
                # This is likely a method that needs 'self' injected
                if parent_class is None:
                    parent_class = get_parent_class(func)
                if parent_class and (not args or not isinstance(args[0], parent_class)):
                    instance = parent_class()
                    return func(instance, *args, **kwargs)
            raise

    return wrapper


# Combined route and injector
def injectable_route(app, route, prefix=None, **options):
    if prefix:
        route = f"{prefix}/{route}"

    def decorator(func):
        injected = injector(func)
        opts = dict(options)
        explicit_subdomains = opts.pop("subdomains", None)
        subdomain_option = opts.get("subdomain")

        # Support multi-subdomain registration while keeping single-subdomain
        # Flask behavior unchanged for existing call sites.
        subdomains = explicit_subdomains
        if subdomains is None and isinstance(subdomain_option, (list, tuple, set)):
            subdomains = list(subdomain_option)
            opts.pop("subdomain", None)

        if subdomains is not None:
            for subdomain in subdomains:
                per_route_opts = dict(opts)
                if subdomain is None or str(subdomain).strip() == "":
                    per_route_opts.pop("subdomain", None)
                else:
                    per_route_opts["subdomain"] = str(subdomain).strip()
                app.route(route, **per_route_opts)(injected)
            return injected

        route_decorator = app.route(route, **opts)
        return route_decorator(injected)

    return decorator


def singleton(cls):
    cls.__singleton__ = True
    return cls
