# Database Abstraction & Adapters

This module provides a **unified database access layer** with adapter support for **MySQL** and **Microsoft SQL Server**. It is designed for consistency, security, and maintainability, and is typically used by creating your own database class that inherits from one of the provided adapters.

Example:

```python
class MyDatabase(MSSQLDatabase):
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=MY-SERVER;"
        "DATABASE=MyDatabase;"
        "UID=myuser;"
        "PWD=mypassword;"
        "Trusted_Connection=no;"
    )
```

This pattern centralizes connection configuration and ensures the same connection settings are used across your application.

---

## Table of Contents

- [Overview](#overview)
- [Adapters](#adapters)
- [Installation](#installation)
- [Creating a Custom Database Class](#creating-a-custom-database-class)
- [Core Methods](#core-methods)
- [Best Practices](#best-practices)
- [Edge Cases & Pitfalls](#edge-cases--pitfalls)
- [Examples](#examples)
- [Error Handling](#error-handling)

---

## Overview

The core abstraction in `` defines a `Protocol` for database access. Each adapter:

- Manages connections
- Executes queries (single and batch)
- Supports parameter binding for safety
- Offers convenience helpers like `.save()` and `.pquery()`
- Optionally provides transaction management (MySQL)

By subclassing an adapter, you lock in configuration and avoid repeating credentials in your code.

---

## Adapters

| Adapter           | File               | Driver            | Special Features                           |
| ----------------- | ------------------ | ----------------- | ------------------------------------------ |
| **MySqlDatabase** | `MySqlDatabase.py` | `mysql.connector` | Transaction context manager                |
| **MSSQLDatabase** | `MSSQLDatabase.py` | `pyodbc`          | Output converter for unsupported datatypes |

---

## Installation

Install the required driver(s):

```bash
pip install pyodbc mysql-connector-python
```

For MSSQL, ensure the correct ODBC driver version is installed on your OS.

---

## Creating a Custom Database Class

**MySQL**

```python
class MyDatabase(MySqlDatabase):
    connection_dict = {
        'host': '127.0.0.1',
        'user': 'root',
        'password': 'secret',
        'database': 'test_db',
        'port': 3306
    }
```

**MSSQL**

```python
class MyDatabase(MSSQLDatabase):
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=MY-SERVER;"
        "DATABASE=MyDatabase;"
        "UID=myuser;"
        "PWD=mypassword;"
        "Trusted_Connection=no;"
    )
```

Usage:

```python
db = MyDatabase()
rows = db.query("SELECT * FROM users")
```

---

## Core Methods

| Method                                             | Purpose                                      |
| -------------------------------------------------- | -------------------------------------------- |
| `.connect()`                                       | Opens a connection and returns a cursor      |
| `.query(sql, *params)`                             | Executes SQL or a QueryBuilder object        |
| `.pquery([{alias: sql}, ...], *params)`            | Executes multiple queries in one round-trip  |
| `.save(table, data, where=None, primary_key="id")` | Insert or update a record                    |
| `.transaction()`                                   | Transaction context manager (**MySQL only**) |
| `.results_or_fail(query, *args)`                   | Query and raise if empty                     |

---

## Best Practices

1. **Parameterize queries** to prevent SQL injection.
2. **Subclass adapters** to centralize connection details.
3. **Reuse the same DB class** across your project to avoid duplicated config.
4. **Use **`` for related queries to reduce network overhead.
5. **Use **`` for CRUD operations instead of hand-written insert/update SQL.
6. Keep transactions **short and isolated**.

---

## Edge Cases & Pitfalls

- Placeholder syntax differs (`%s` for MySQL, internally converted to `?` for MSSQL).
- MySQL transaction context is not available for MSSQL.
- `.save()` raises `ValueError` if no data is provided.
- `WHERE IN` clauses expand automatically when you pass lists.
- Ensure parameter counts match placeholder counts in `pquery`.

---

## Examples

```python
# Simple query
db = MyDatabase()
users = db.query("SELECT * FROM users")

# Parameterized query
db.query("SELECT * FROM users WHERE id = %s", 1)

# Insert new record
new_user_id = db.save("users", {"name": "John"})

# Update existing record
db.save("users", {"email": "new@example.com"}, where={"id": 5})

# Batch queries
data = db.pquery([
    {"admins": "SELECT * FROM users WHERE role = 'admin'"},
    {"guests": "SELECT * FROM users WHERE role = 'guest'"}
])

# MySQL transaction
with db.transaction():
    db.query("UPDATE accounts SET balance = balance - %s WHERE id = %s", 100, 1)
    db.query("UPDATE accounts SET balance = balance + %s WHERE id = %s", 100, 2)
```

---

## Error Handling

- `NoResultsFound` is raised by `.results_or_fail()` when no rows are returned.
- Database driver exceptions bubble up (e.g., `pyodbc.Error`, `mysql.connector.Error`).
- Wrap critical operations in `try/except` to handle errors gracefully.

```python
try:
    result = db.results_or_fail("SELECT * FROM orders WHERE id = %s", 999)
except NoResultsFound:
    print("Order not found.")
```

