from framework1.database.discover import discover_models
from framework1.database.migrations import (
    get_model_schema_snapshot,
    load_schema_history,
    save_schema_history,
    get_last_known_fields,
    diff_model_to_history,
    generate_create_table_sql
)
def migrate(dry_run=False, replay=False):
    models = discover_models("lib")
    print(f"[info] Discovered {len(models)} models.")

    for model in models:
        print(f"\n[info] Checking `{model.__name__}`...")
        db = model.__database__()
        if hasattr(model, "__ignore_migration__"):
            if getattr(model, "__ignore_migration__"):
                print(f"[warn] `{model.__name__}` migration is ignored.")
                continue
        current = get_model_schema_snapshot(model)
        saved_schema = load_schema_history(model)
        last_fields = get_last_known_fields(saved_schema)

        if replay or not last_fields:
            try:
                sql = generate_create_table_sql(model)
            except Exception as e:
                print(f"[error] Error generating SQL for `{model.__name__}`: {e}")
                continue
            print(" ->", sql)
            if not dry_run:
                db.query(sql)
                db.connection.commit()
                save_schema_history(model, current)
                print(f"[ok] `{current['table']}` created.\n")
            else:
                print("[warn] Dry run: table creation not executed.\n")
            continue

        changes = diff_model_to_history(model, current, last_fields)
        if not changes:
            print(f"[ok] `{model.__name__}` is up to date.")
            continue

        for change in changes:
            if change["op"] == "remove":
                sql = f"ALTER TABLE `{current['table']}` DROP COLUMN `{change['field']}`;"
            elif change["op"] == "modify":
                sql = f"ALTER TABLE `{current['table']}` MODIFY COLUMN `{change['field']}` {change['sql_type']};"
            else:  # add
                sql = f"ALTER TABLE `{current['table']}` ADD COLUMN `{change['field']}` {change['sql_type']};"

            print(" ->", sql)
            if not dry_run:
                db.query(sql)
                db.connection.commit()
            else:
                print("[warn] Dry run: change not executed.")

        save_schema_history(model, current)
        print(f"[ok] `{model.__name__}` migrated.\n")
