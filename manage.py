import argparse
import os
import json
import subprocess
from typing import List

from framework1.cli.database import create_database_service
from framework1.cli.form_related import generate_form
from framework1.cli.generate_model import generate_model
from framework1.cli.migrate import migrate
from framework1.cli.resource_handler import create_resource_handler
from framework1.cli.structure import create_symbolic_link
from framework1.cli.structure import create_lib_structure


def main():
    parser = argparse.ArgumentParser(description="Project management tool")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Show SQL without executing")
    migrate_parser.add_argument("--replay", action="store_true", help="Recreate tables from scratch")

    # Generate model command
    generate_parser = subparsers.add_parser("make:model", help="Generate new model")
    generate_parser.add_argument("name", help="Model name (PascalCase)")
    generate_parser.add_argument("--fields", nargs="+", help="Field definitions in format name:type:args")
    generate_parser.add_argument("--output", default="lib/models", help="Output directory")

    # Init command
    init_parser = subparsers.add_parser("make:project", help="Initialize project structure")
    init_parser.add_argument("--framework-path", help="Path to framework library for symbolic link")

    # Resource command
    resource_parser = subparsers.add_parser("make:resource", help="Create new resource handler")
    resource_parser.add_argument("name", help="Resource name")
    resource_parser.add_argument("database_name", help="Database name")
    resource_parser.add_argument('--fields', '-f', nargs='+',
                       help='Field definitions in format name:type:args. Example: name:CharField:max_length=100')

    # Generate Form Command
    generate_form_parser = subparsers.add_parser("make:form", help="Generate form based on a resource model")
    generate_form_parser.add_argument("resource_name", type=str, help="The resource folder name")
    
    # Generate Form Command
    generate_crud_form_parser = subparsers.add_parser("make:crud", help="Generate crud (Table + Form) based on a resource model")
    generate_crud_form_parser.add_argument("resource_name", type=str, help="The resource folder name")

    # Generate Table Command
    generate_table_parser = subparsers.add_parser("make:table", help="Generate table based on a resource model")
    generate_table_parser.add_argument("resource_name", type=str, help="The resource folder name")

    # Database service command
    db_parser = subparsers.add_parser("make:database", help="Create a new database service")
    db_parser.add_argument("name", help="Name of the database service")
    db_parser.add_argument("type", choices=["mysql", "mssql"], help="Database type")

    args = parser.parse_args()

    if args.command == "make:database":
        create_database_service(args.name, args.type)

    elif args.command == "make:form":
        generate_form(args.resource_name)

    elif args.command == "make:table":
        generate_form(args.resource_name, is_table=True)

    elif args.command == "make:crud":
        generate_form(args.resource_name, is_table=False)
        generate_form(args.resource_name, is_table=True)



    elif args.command == "migrate":
        migrate(dry_run=args.dry_run, replay=args.replay)

    elif args.command == "make:model":
        fields = []
        if args.fields:
            for field_def in args.fields:
                parts = field_def.split(":")
                field = {"name": parts[0], "type": parts[1]}
                if len(parts) > 2:
                    for arg in parts[2].split(","):
                        if "=" in arg:
                            key, value = arg.split("=")
                            if value.lower() == "true":
                                value = True
                            elif value.lower() == "false":
                                value = False
                            elif value.isdigit():
                                value = int(value)
                            field[key] = value
                fields.append(field)
        else:
            fields = [
                {"name": "id", "type": "IntegerField", "primary_key": True},
                {"name": "created_at", "type": "DateTimeField", "default": "CURRENT_TIMESTAMP"},
                {"name": "updated_at", "type": "DateTimeField", "default": "CURRENT_TIMESTAMP"}
            ]
        generate_model(args.name, fields, args.output)

    elif args.command == "make:project":
        create_lib_structure()
        if args.framework_path:
            create_symbolic_link(args.framework_path)

    elif args.command == "make:resource":
        resources = args.name.split(",")
        for resource in resources:
            create_resource_handler(resource, args.database_name, args.fields)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
