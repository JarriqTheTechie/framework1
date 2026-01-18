import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

# Provide lightweight stubs so optional DB drivers are not required for import.
sys.modules.setdefault("pyodbc", mock.Mock())
sys.modules.setdefault("_mysql_connector", mock.Mock())
sys.modules.setdefault("mysql", mock.Mock())
sys.modules.setdefault("mysql.connector", mock.Mock(connect=mock.Mock()))
import typing
if not hasattr(typing, "override"):
    typing.override = lambda x=None: x
sys.modules.setdefault("logly", mock.Mock(logger=mock.Mock()))
sys.modules.setdefault("flask", mock.Mock(request=mock.Mock(), session=mock.Mock(), flash=mock.Mock(), get_flashed_messages=mock.Mock()))

from cli import database, form_related, migrate, resource_handler, structure


@contextlib.contextmanager
def temp_cwd(path: Path):
    """Temporarily change the working directory."""
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


@contextlib.contextmanager
def suppress_output():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


class DummyDB:
    def __init__(self):
        self.executed = []
        self.committed = False
        self.connection = SimpleNamespace(commit=self._commit)

    def query(self, sql, *args):
        self.executed.append(sql)

    def _commit(self):
        self.committed = True


class TestStructure(TestCase):
    def test_create_lib_structure_copies_package_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            package_root = base / "venv" / "Lib" / "site-packages" / "framework1"
            package_root.mkdir(parents=True)
            # Seed package assets
            (package_root / "base.html").write_text("base")
            (package_root / "styles.html").write_text("styles")
            (package_root / ".env").write_text("env")
            (package_root / "users").mkdir()
            (package_root / "users" / "placeholder.txt").write_text("u")
            (package_root / "ADAuth.py").write_text("ad")
            (package_root / "ddd").mkdir(parents=True)
            (package_root / "ddd" / "DESBus.py").write_text("desbus")
            (package_root / "DomainEventOutbox.py").write_text("outbox")
            (package_root / "DomainEventBus.py").write_text("bus")
            (package_root / "ViewState.py").write_text("viewstate")
            (package_root / "dsl").mkdir()
            (package_root / "dsl" / "InformationSchema.py").write_text("info")

            original_prefix = sys.prefix
            sys.prefix = str(base / "venv")
            try:
                with temp_cwd(base), suppress_output():
                    structure.create_lib_structure()
            finally:
                sys.prefix = original_prefix

            assert (base / "lib/handlers/base.html").read_text() == "base"
            assert (base / "lib/handlers/styles.html").read_text() == "styles"
            assert (base / ".env").read_text() == "env"
            # Copies use venv_path now (not the current .env path)
            assert (base / "lib/services/ADAuth.py").read_text() == "ad"
            assert (base / "lib/services/DESBus.py").read_text() == "desbus"
            assert (base / "lib/services/DomainEventOutbox.py").read_text() == "outbox"
            assert (base / "lib/services/DomainEventBus.py").read_text() == "bus"
            assert (base / "lib/models/ViewState.py").read_text() == "viewstate"
            assert (base / "lib/models/InformationSchema.py").read_text() == "info"


class TestDatabase(TestCase):
    def test_create_database_service_mysql_has_dual_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with temp_cwd(base), suppress_output():
                database.create_database_service("My", "mysql")
            content = (base / "lib/services/MyDatabase.py").read_text()
            assert "framework1.core_services.database.MySqlDatabase" in content
            assert "framework1.core_services.MySqlDatabase" in content

    def test_create_database_service_mssql_has_dual_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with temp_cwd(base), suppress_output():
                database.create_database_service("Ms", "mssql")
            content = (base / "lib/services/MsDatabase.py").read_text()
            assert "framework1.core_services.database.MSSQLDatabase" in content
            assert "framework1.core_services.MSSQLDatabase" in content

    def test_invalid_name_raises(self):
        with self.assertRaises(ValueError):
            database.create_database_service("1bad", "mysql")


class TestResourceHandler(TestCase):
    def test_create_resource_handler_generates_consistent_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with temp_cwd(base), suppress_output():
                resource_handler.create_resource_handler(
                    "widget",
                    database="MyDB",
                    field_definitions=["name:CharField", "active:BooleanField:default=true"],
                )

            controller = (base / "lib/handlers/widgets/WidgetController.py").read_text()
            assert "/widgets/create" in controller  # POST route matches GET slug
            assert "abort(404)" in controller  # Not-found guard is present
            assert "def WidgetEdit(self, id: int" in controller
            assert "validate_csrf" in controller
            assert "_ensure_permission" in controller

            create_template = (base / "lib/handlers/widgets/templates/create.html").read_text()
            assert "csrf_token" in create_template

    def test_invalid_resource_name_raises(self):
        with self.assertRaises(ValueError):
            resource_handler.create_resource_handler("123bad", database="MyDB", field_definitions=[])


class TestFormRelated(TestCase):
    def _write_model(self, base: Path, snake_plural: str, class_name: str):
        model_path = base / "lib" / "handlers" / snake_plural / "models"
        model_path.mkdir(parents=True, exist_ok=True)
        model_file = model_path / f"{class_name}.py"
        model_file.write_text(
            "from framework1.database.ActiveRecord import ActiveRecord\n"
            "from framework1.database.fields.Fields import IntegerField, CharField\n"
            f"class {class_name}(ActiveRecord):\n"
            "    id = IntegerField(primary_key=True)\n"
            "    name = CharField()\n"
        )
        return model_file

    def test_generate_form_avoids_duplicate_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            snake_plural = "widgets"
            self._write_model(base, snake_plural, "Widget")
            forms_dir = base / "lib" / "handlers" / snake_plural / "forms"
            forms_dir.mkdir(parents=True, exist_ok=True)

            with temp_cwd(base), suppress_output():
                form_related.generate_form("widget", is_table=False)

            form_content = (forms_dir / "WidgetForm.py").read_text()
            assert form_content.count("from framework1.dsl.FormDSL.TextField import TextField") == 1

    def test_generate_table_and_infolist(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            snake_plural = "widgets"
            self._write_model(base, snake_plural, "Widget")
            tables_dir = base / "lib" / "handlers" / snake_plural / "tables"
            infolist_dir = base / "lib" / "handlers" / snake_plural / "infolists"
            tables_dir.mkdir(parents=True, exist_ok=True)
            infolist_dir.mkdir(parents=True, exist_ok=True)

            with temp_cwd(base), suppress_output():
                form_related.generate_form("widget", is_table=True)

            table_content = (tables_dir / "WidgetTable.py").read_text()
            infolist_content = (infolist_dir / "WidgetInfoList.py").read_text()
            assert "TextColumn('name')" in table_content
            assert "InfoListField('name')" in infolist_content


class TestMigrate(TestCase):
    def test_migrate_replay_uses_create_sql_and_commits(self):
        dummy_db = DummyDB()

        class DummyModel:
            __name__ = "Dummy"
            __database__ = staticmethod(lambda: dummy_db)

        with mock.patch.object(migrate, "discover_models", return_value=[DummyModel]):
            with mock.patch.object(migrate, "get_model_schema_snapshot", return_value={"table": "dummy"}):
                with mock.patch.object(migrate, "load_schema_history", return_value=[]):
                    with mock.patch.object(migrate, "get_last_known_fields", return_value={}):
                        with mock.patch.object(migrate, "generate_create_table_sql", return_value="CREATE TABLE dummy();"):
                            with suppress_output():
                                migrate.migrate(dry_run=False, replay=True)

        assert dummy_db.executed == ["CREATE TABLE dummy();"]
        assert dummy_db.committed is True
