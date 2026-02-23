import importlib
import inspect
import pkgutil
from pathlib import Path

from framework1.service_container._ServiceContainer import ServiceContainer


def to_class(path: str) -> object | None:
    """
    Converts string class path to a Python class.

    Args:
        path (str): The string representing the class path.

    Returns:
        Union[type, None]: The Python class if found, otherwise None.
    """
    if not path or "." not in path:
        return None
    module_path, class_name = path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except Exception:
        return None
    class_instance = getattr(module, class_name, None)
    return class_instance if inspect.isclass(class_instance) else None


def _register_service(app, service_class):
    if not service_class:
        return
    if getattr(service_class, "__singleton__", False):
        app.container.add(service_class.__name__, service_class, singleton=True)
    else:
        app.container.add(service_class.__name__, service_class)


def _load_service_from_module(app, module_name: str, class_name: str, debug=False):
    service_class = to_class(f"{module_name}.{class_name}")
    if not service_class:
        if debug:
            app.logger.debug(f"[Framework1] Skipping unresolved service: {module_name}.{class_name}")
        return
    _register_service(app, service_class)


def init_container(app, services_path: str = "lib/services", debug=False):
    app.container = ServiceContainer()

    # Register Framework1 core services directly from the installed package.
    import framework1.core_services as core_services_pkg
    for module_info in pkgutil.iter_modules(core_services_pkg.__path__):
        service_name = module_info.name
        if service_name.startswith("__"):
            continue
        module_name = f"{core_services_pkg.__name__}.{service_name}"
        _load_service_from_module(app, module_name, service_name, debug=debug)

    paths = services_path.split(";") if ";" in services_path else [services_path]
    cwd = Path.cwd()

    for path in paths:
        services_dir = (cwd / path).resolve()
        if not services_dir.exists() or not services_dir.is_dir():
            if debug:
                app.logger.debug(f"[Framework1] Service path not found: {services_dir}")
            continue

        for service_file in services_dir.glob("*.py"):
            if service_file.stem.startswith("__"):
                continue

            relative_path = service_file.with_suffix("").relative_to(cwd)
            module_name = ".".join(relative_path.parts)
            _load_service_from_module(app, module_name, service_file.stem, debug=debug)

    return app
