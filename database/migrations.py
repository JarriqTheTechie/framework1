import json
from pathlib import Path
from typing import Any, Dict, List
from framework1.database.ActiveRecord import ActiveRecord


def get_model_schema_snapshot(model_cls: type[ActiveRecord]) -> dict[str, Any]:
    """Get current schema snapshot of a model"""
    fields = model_cls.get_fields()
    return {
        "table": model_cls.__table__,
        "primary_key": model_cls.__primary_key__,
        "fields": {
            name: {
                "sql_type": field.get_sql_type(),
                "nullable": field.nullable,
                "unique": field.unique,
                "default": field.default,
                "primary_key": field.primary_key,
            }
            for name, field in fields.items()
        }
    }


def get_schema_path(model_cls: type[ActiveRecord]) -> Path:
    """Get path to schema file for a model"""
    return Path(f".migrations/schemas/{model_cls.__name__}.schema.json")


def load_schema_history(model_cls: type[ActiveRecord]) -> dict:
    """Load saved schema for a model"""
    path = get_schema_path(model_cls)
    if not path.exists():
        return {"table": model_cls.__table__, "fields": {}}

    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, "r", encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"table": model_cls.__table__, "fields": {}}


def save_schema_history(model_cls: type[ActiveRecord], schema: dict):
    """Save current schema for a model"""
    path = get_schema_path(model_cls)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding='utf-8') as f:
        json.dump(schema, f, indent=2)


def get_last_known_fields(history: dict) -> Dict[str, Dict[str, Any]]:
    """Get the saved field definitions"""
    return history.get("fields", {})


def diff_model_to_history(
        model_cls: type[ActiveRecord],
        current: dict,
        last_fields: dict
) -> List[Dict[str, Any]]:
    """Compare current schema to saved schema and return needed changes"""
    changes = []

    # Check for new or modified fields
    for name, meta in current["fields"].items():
        if name not in last_fields:
            changes.append({
                "op": "add",
                "field": name,
                "sql_type": meta["sql_type"]
            })
        elif meta != last_fields[name]:
            changes.append({
                "op": "modify",
                "field": name,
                "sql_type": meta["sql_type"]
            })

    # Check for removed fields
    for name in last_fields:
        if name not in current["fields"]:
            changes.append({
                "op": "remove",
                "field": name
            })

    return changes


def generate_create_table_sql(model_cls: type[ActiveRecord]) -> str:
    """Generate CREATE TABLE SQL from model definition"""
    fields = model_cls.get_fields()
    if not fields:
        raise ValueError(f"{model_cls.__name__} has no declared fields.")

    columns = []
    pk = None

    for name, field in fields.items():
        col_def = f"`{name}` {field.get_sql_type()}"

        if not field.nullable:
            col_def += " NOT NULL"
        if field.unique:
            col_def += " UNIQUE"
        if field.default is not None:
            d = field.default
            if isinstance(d, str) and d.upper() in ("CURRENT_TIMESTAMP", "NOW()"):
                col_def += f" DEFAULT {d}"
            elif isinstance(d, (int, float)):
                col_def += f" DEFAULT {d}"
            else:
                col_def += f" DEFAULT '{d}'"

        if field.primary_key:
            pk = name

        columns.append(col_def)

    if pk:
        columns.append(f"PRIMARY KEY (`{pk}`)")

    table_name = model_cls.__table__
    return f"CREATE TABLE IF NOT EXISTS `{table_name}` (\n  " + ",\n  ".join(columns) + "\n);"


def replay_events_to_create_table(history: dict, table_name: str) -> str:
    """Generate CREATE TABLE SQL for fresh table creation"""
    return generate_create_table_sql(history["model_cls"])