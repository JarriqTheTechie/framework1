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


def service_resolver(param, func_name: str):
    """Resolves and retrieves the appropriate service from the container."""
    if not has_app_context():
        raise RuntimeError(f"No Flask app context available for injecting '{param.name}' in '{func_name}'")

    if param.annotation is inspect.Parameter.empty:
        return None

    service_name = param.annotation if isinstance(param.annotation, str) else param.annotation.__name__

    container = current_app.container
    if not (container.has(service_name) or container.has_singleton(service_name)):
        raise ValueError(
            f"[Injector] Cannot resolve service '{service_name}' for parameter '{param.name}' in '{func_name}'. "
            f"Ensure it is registered in the container."
        )

    return container.get(service_name)


def injector(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        sig = inspect.signature(func)
        for name, param in sig.parameters.items():
            if name in kwargs:  # already provided by Flask (e.g. user_id)
                continue
            service = service_resolver(param, func.__name__)
            if service is not None:
                kwargs[name] = service
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "missing 1 required positional argument: 'self'" in str(e):
                # This is likely a method that needs 'self' injected
                parent_class = get_parent_class(func)
                if parent_class:
                    instance = parent_class()
                    return func(instance, *args, **kwargs)
            raise

    return wrapper


# Combined route and injector
def injectable_route(app, route, prefix=None, **options):
    if prefix:
        route = f"{prefix}/{route}"

    def decorator(func):
        # print(func.__name__)
        route_decorator = app.route(route, **options)
        return route_decorator(
            injector(func)
        )

    return decorator


def singleton(cls):
    cls.__singleton__ = True
    return cls
