import importlib
import inspect
import sys
from pathlib import Path

from framework1.core_services.Request import Request
from framework1.service_container._Injector import injectable_route
from framework1.dsl.table.core import Table
from app import app


def _discover_tables(base_dir: str = "lib/handlers"):
    tables = []
    handlers_dir = Path(base_dir)
    project_root = handlers_dir.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    for file in handlers_dir.rglob("tables/*.py"):
        if file.name == "__init__.py":
            continue

        module_path = ".".join(file.with_suffix("").relative_to(project_root).parts)
        try:
            module = importlib.import_module(module_path)
        except Exception:
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Table) and obj is not Table and obj.__module__ == module.__name__:
                tables.append(obj)

    return tables


@injectable_route(app, "/f1/export-excel", methods=["GET"])
def TableExportExcel(request: Request):
    table_name = request.input("table")
    model_name = request.input("model")
    if not table_name and not model_name:
        return {"success": False, "message": "Table or model required"}

    table_cls = None
    for candidate in _discover_tables():
        if table_name and candidate.__name__ == table_name:
            table_cls = candidate
            break
        if model_name and getattr(candidate, "model", None) and candidate.model.__name__ == model_name:
            table_cls = candidate
            break

    if not table_cls:
        return {"success": False, "message": "Unknown table/model"}

    model_cls = getattr(table_cls, "model", None)
    if not model_cls or not getattr(model_cls, "__exportable__", False):
        return {"success": False, "message": "Model not exportable"}

    table = table_cls()
    if table.query:
        if hasattr(table.query, "all"):
            table.data = table.query.all()
        elif hasattr(table.query, "db") and hasattr(table.query, "get"):
            table.data = table.query.db.query(*table.query.get())
        else:
            table.data = table.query
    return table.export_excel(filename=f"{table_cls.__name__}.xlsx")


@injectable_route(app, "/f1/delete-bulk", methods=["GET"])
def TableDeleteBulk(request: Request):
    # TODO: WORK ON BULK ACTIONS
    ids = request.to_list("ids", cast=int)
    model_name = request.input("model")
    table_name = request.input("table")
    if not ids or (not model_name and not table_name):
        return {"success": False, "message": "Invalid request"}

    table_cls = None
    for candidate in _discover_tables():
        if table_name and candidate.__name__ == table_name:
            table_cls = candidate
            break
        if model_name and getattr(candidate, "model", None) and candidate.model.__name__ == model_name:
            table_cls = candidate
            break

    if not table_cls or not getattr(table_cls, "model", None):
        return {"success": False, "message": "Unknown table/model"}

    table_cls.model().where_in("id", ids).delete()
    return {"success": True}
