import importlib
import inspect
from pathlib import Path
from framework1.service_container._ServiceLoader import to_class
import sys
from framework1.database.ActiveRecord import ActiveRecord


def discover_models(lib_path: str = "lib"):
    models = []
    base_dir = Path(lib_path)

    project_root = base_dir.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    def _import_module(file_path: Path):
        # Convert path to module path format, starting from lib
        parts = file_path.relative_to(base_dir).with_suffix('').parts
        module_name = f"lib.{'.'.join(parts)}"
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))

        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)

            spec.loader.exec_module(module)
            return module


    def _scan_models_directory(models_dir: Path):
        for item in models_dir.iterdir():

            if item.is_file() and item.suffix == '.py' and not item.stem.startswith('__'):
                module = _import_module(item)
                if module:
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, ActiveRecord) and obj != ActiveRecord:
                            models.append(obj)

    def _find_models_folders(directory: Path):
        if not directory.exists():
            return

        # Check all subdirectories
        for item in directory.iterdir():
            if item.is_dir() and not item.name.startswith('__'):
                # If we find a "models" directory, scan it
                if item.name == "models":
                    _scan_models_directory(item)
                # Continue searching in subdirectories
                _find_models_folders(item)

    _find_models_folders(base_dir)
    return models
