import os


def create_database_service(name: str, db_type: str):
    """Create a new database service file."""
    services_path = os.path.join("lib", "services")
    os.makedirs(services_path, exist_ok=True)

    if db_type.lower() == "mysql":
        content = f'''from framework1.core_services.MySqlDatabase import MySqlDatabase
from framework1.interfaces.LifecycleAware import LifecycleAware

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
    elif db_type.lower() == "mssql":
        content = f'''from framework1.core_services.MSSQLDatabase import MSSQLDatabase
from framework1.interfaces.LifecycleAware import LifecycleAware

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

    with open(filepath, 'w') as f:
        f.write(content)

    print(f"✨ Created database service: {filepath}")