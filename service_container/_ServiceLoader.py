import pprint

import glob
import os
import pydoc
from pydoc import locate

from framework1.service_container._ServiceContainer import ServiceContainer


def to_class(path: str) -> object | None:
    """
    Converts string class path to a Python class.

    Args:
        path (str): The string representing the class path.

    Returns:
        Union[type, None]: The Python class if found, otherwise None.
    """
    try:
        class_instance = locate(path)
    except ImportError:
        print('Module does not exist')
        return None
    except pydoc.ErrorDuringImport as e:
        print(f"Error during import: {e} for {path}")
    return class_instance


def init_container(app, services_path: str = "lib/services", debug=False):
    import sys
    app.container = ServiceContainer()
    venv_path = sys.prefix

    core_services = glob.glob(f"{venv_path}/Lib/site-packages/framework1/core_services/*.py")
    for service in core_services:
        # get the service class name
        service_class_name = service.split("/")[-1][:-3].split("\\")[-1]
        service_module_name = service.replace("/", ".").replace("\\", ".")[:-3]
        start_index = service_module_name.find("framework1")
        final_service_module_name = service_module_name[start_index:]

        service_class = to_class(f"{final_service_module_name}.{service_class_name}")
        if service_class:
            if getattr(service_class, "__singleton__", False):
                app.container.add(service_class.__name__, service_class, singleton=True)
            else:
                app.container.add(service_class.__name__, service_class)

    
    services = glob.glob(f"{os.getcwd()}/{services_path}/*.py")
    for service in services:
        # get the service class name
        service_class_name = service.split("/")[-1][:-3].split("\\")[-1]
        service_module_name = service.replace("/", ".").replace("\\", ".")[:-3]
        service_path_dotted = services_path.replace("/", ".").replace("\\", ".")
        start_index = service_module_name.find(service_path_dotted)
        final_service_module_name = service_module_name[start_index:]

        print(f"{final_service_module_name}.{service_class_name}")
        service_class = to_class(f"{final_service_module_name}.{service_class_name}")
        if service_class:

            if getattr(service_class, "__singleton__", False):
                app.container.add(service_class.__name__, service_class, singleton=True)
            else:
                app.container.add(service_class.__name__, service_class)
    return app