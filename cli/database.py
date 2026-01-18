import os
import re


def _validate_identifier(name: str):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid name '{name}'. Use letters, numbers, and underscores; must start with a letter/underscore.")


def _db_import_block(driver: str) -> str:
    """Return a defensive import block for MySQL/MSSQL drivers across layouts."""
    class_name = f"{driver}Database"
    return f"""try:
    from framework1.core_services.database.{class_name} import {class_name}
except ImportError:
    from framework1.core_services.{class_name} import {class_name}
"""


def create_database_service(name: str, db_type: str, overwrite: bool = False):
    """Create a new database service file."""
    _validate_identifier(name)
    services_path = os.path.join("lib", "services")
    os.makedirs(services_path, exist_ok=True)

    db_type_lower = db_type.lower()
    if db_type_lower == "mysql":
        imports = _db_import_block("MySql")
        content = f'''{imports}

class {name}Database(MySqlDatabase):
    env = "prod"
    connection_dict = dict(
        host="HOST NAME",
        port=3306,
        user="YOUR MYSQL DB USERNAME",
        password="YOUR PASSWORD",
        database="DATABASE NAME",
    )
'''
    elif db_type_lower == "mssql":
        imports = _db_import_block("MSSQL")
        content = f'''{imports}


class {name}Database(MSSQLDatabase):
    connection_string = 'DRIVER={{ODBC Driver 17 for SQL Server}};' \\
                       'SERVER=SERVER NAME;' \\
                       'PORT=1433;' \\
                       'DATABASE=DATABASE NAME;' \\
                       'Trusted_Connection=yes;' \\
                       'Connection Timeout=10;'
'''
    else:
        raise ValueError(f"Unsupported database type: {db_type}")

    filename = f"{name}Database.py"
    filepath = os.path.join(services_path, filename)

    if os.path.exists(filepath) and not overwrite:
        print(f"[skip] {filepath} already exists. Pass overwrite=True to replace.")
        return filepath

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[ok] Created database service: {filepath}")
    return filepath
