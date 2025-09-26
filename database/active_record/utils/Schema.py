import importlib
import os

from framework1.database.fields.Fields import Field


class ActiveRecordUtilitiesSchema():
    
            sql = getattr(module, direction)()
            db = cls.__database__()
            db.query(sql)
            db.connection.commit()
            print(f"✔ [{direction.upper()}] {file}")

    def get_table_fields(self) -> list[dict]:
        """
        Get all fields/columns from the current database table.

        Returns:
            list[dict]: List of dictionaries containing field information with keys:
                - Field: Column name
                - Type: Data type
                - Null: Whether the field can be NULL
                - Key: Index type (PRI, UNI, MUL, etc.)
                - Default: Default value
                - Extra: Additional information

        Example:
            fields = model.get_table_fields()
            for field in fields:
                print(f"Column: {field['Field']}, Type: {field['Type']}")
        """
        if not hasattr(self, '__table__') or not self.__table__:
            raise ValueError("No table name defined for this model")

        # Get the database instance
        db = self.__database__()

        # For MySQL
        if getattr(self, '__driver__', '').lower() == 'mysql':
            query = f"DESCRIBE `{self.__table__}`"
        # For PostgreSQL
        elif getattr(self, '__driver__', '').lower() == 'postgresql':
            query = f"""
                SELECT 
                    column_name as "Field",
                    data_type as "Type",
                    CASE 
                        WHEN is_nullable = 'YES' THEN 'YES'
                        ELSE 'NO'
                    END as "Null",
                    CASE 
                        WHEN column_default IS NOT NULL THEN column_default
                        ELSE ''
                    END as "Default",
                    CASE 
                        WHEN pk.column_name IS NOT NULL THEN 'PRI'
                        WHEN uk.column_name IS NOT NULL THEN 'UNI'
                        WHEN fk.column_name IS NOT NULL THEN 'MUL'
                        ELSE ''
                    END as "Key",
                    '' as "Extra"
                FROM information_schema.columns c
                LEFT JOIN (
                    SELECT ccu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.table_name = '{self.__table__}' AND tc.constraint_type = 'PRIMARY KEY'
                ) pk ON c.column_name = pk.column_name
                LEFT JOIN (
                    SELECT ccu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.table_name = '{self.__table__}' AND tc.constraint_type = 'UNIQUE'
                ) uk ON c.column_name = uk.column_name
                LEFT JOIN (
                    SELECT ccu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.table_name = '{self.__table__}' AND tc.constraint_type = 'FOREIGN KEY'
                ) fk ON c.column_name = fk.column_name
                WHERE table_name = '{self.__table__}'
                ORDER BY ordinal_position
            """
        # For MSSQL
        elif getattr(self, '__driver__', '').lower() == 'mssql':
            query = f"""
                SELECT 
                    c.name as 'Field',
                    t.name as 'Type',
                    CASE WHEN c.is_nullable = 1 THEN 'YES' ELSE 'NO' END as 'Null',
                    CASE 
                        WHEN pk.column_id IS NOT NULL THEN 'PRI'
                        WHEN uk.column_id IS NOT NULL THEN 'UNI'
                        WHEN fk.parent_column_id IS NOT NULL THEN 'MUL'
                        ELSE ''
                    END as 'Key',
                    ISNULL(dc.definition, '') as 'Default',
                    CASE 
                        WHEN c.is_identity = 1 THEN 'auto_increment'
                        ELSE ''
                    END as 'Extra'
                FROM sys.columns c
                INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
                INNER JOIN sys.objects o ON c.object_id = o.object_id
                LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
                LEFT JOIN sys.index_columns pk ON c.object_id = pk.object_id 
                    AND c.column_id = pk.column_id 
                    AND pk.index_id = 1
                LEFT JOIN sys.index_columns uk ON c.object_id = uk.object_id 
                    AND c.column_id = uk.column_id 
                    AND uk.index_id > 1
                LEFT JOIN sys.foreign_key_columns fk ON c.object_id = fk.parent_object_id 
                    AND c.column_id = fk.parent_column_id
                WHERE o.name = '{self.__table__}'
                ORDER BY c.column_id
            """
        else:
            raise ValueError(f"Unsupported database driver: {getattr(self, '__driver__', 'unknown')}")

        return db.query(query)

    def print_model(self) -> str:
        """
        Generate a string representation of the model using database table fields.

        Returns:
            str: Formatted string showing model structure and field information

        Example:
            print(model.print_model())
        """
        fields = self.get_table_fields()
        if not fields:
            return "No fields found in table"

        # Get class name and table info
        class_name = self.__class__.__name__
        table_name = getattr(self, '__table__', 'unknown')
        driver = getattr(self, '__driver__', 'unknown')
        database = getattr(self, '__database__', 'unknown').__name__

        # Build the model string
        lines = [
            f"class {class_name}(ActiveRecord):",
            f"    __table__ = \"{table_name}\"",
            f"    __driver__ = \"{driver}\"",
            f"    __database__ = {database}",
            f"    __primary_key__ = \"{self.get_primary_key_column()}\"\n"
        ]

        # Add fields
        for field in fields:
            # Determine field type
            field_type = self._get_field_type(field['Type'])

            # Build field arguments
            args = []
            if field['Key'] == 'PRI':
                args.append('primary_key=True')
            if field['Null'] == 'YES':
                args.append('nullable=True')
            if field['Default'] is not None:
                if 'CURRENT_TIMESTAMP' in str(field['Default']):
                    args.append('default="CURRENT_TIMESTAMP"')
                elif field['Default'] != '':
                    args.append(f'default="{field["Default"]}"')
            if 'varchar' in field['Type'].lower():
                length = field['Type'].split('(')[1].split(')')[0]
                args.append(f'max_length={length}')
            if field['Extra']:
                if 'auto_increment' in field['Extra'].lower():
                    args.append('auto_increment=True')

            # Format field line
            args_str = ", ".join(args)
            field_line = f"    {field['Field']} = {field_type}({args_str})"
            lines.append(field_line)

        # Add create_table section
        lines.extend([
            "",
            "if __name__ == \"__main__\":",
            f"    {class_name}.create_table()  # This will create the table directly"
        ])

        return "\n".join(lines)

    def _get_field_type(self, db_type: str) -> str:
        """Helper method to convert database types to Field classes"""
        db_type = db_type.lower()
        if 'int' in db_type:
            return 'IntegerField'
        elif 'varchar' in db_type or 'text' in db_type or 'char' in db_type:
            return 'CharField'
        elif 'datetime' in db_type or 'timestamp' in db_type:
            return 'DateTimeField'
        elif 'decimal' in db_type or 'numeric' in db_type or 'float' in db_type:
            return 'DecimalField'
        elif 'bool' in db_type:
            return 'BooleanField'
        elif 'json' in db_type:
            return 'JsonField'
        else:
            return 'Field'

    def print_table(self) -> str:
        """
        Generate a string representation of a Table class using database table fields.

        Returns:
            str: Formatted string showing table structure
        """
        fields = self.get_table_fields()
        if not fields:
            return "No fields found in table"

        # Get class name and model info
        class_name = self.__class__.__name__
        table_class = f"{class_name}Table"

        # Build the table class string
        lines = [
            f"from framework1.dsl.Table import Table, Field",
            f"from {self.__module__} import {class_name}\n",
            f"class {table_class}(Table):",
            f"    model = {class_name}",
            f"    table_class = \"table table-striped table-hover mt-3\"\n",
            f"    def schema(self):",
            f"        return ["
        ]

        # Add fields
        for field in fields:
            args = []
            field_name = field['Field']

            # Add label if different from field name
            if field_name != field_name.title():
                args.append(f"label='{field_name.title()}'")

            # Format field line
            args_str = ", ".join(args)
            if args_str:
                field_line = f"            Field('{field_name}').{args_str},"
            else:
                field_line = f"            Field('{field_name}'),"
            lines.append(field_line)

        lines.append("        ]")
        return "\n".join(lines)

    def print_form(self) -> str:
        """
        Generate a string representation of a Form class using database table fields.

        Returns:
            str: Formatted string showing form structure
        """
        fields = self.get_table_fields()
        if not fields:
            return "No fields found in table"

        # Get class name info
        class_name = self.__class__.__name__
        form_class = f"{class_name}Form"

        # Build the form class string
        lines = [
            f"from framework1.core_services.Form import Form",
            f"from framework1.core_services.FormFields import *\n",
            f"class {form_class}(Form):",
            f"    def fields(self):",
            f"        return [            'FieldGroup('{class_name} Fields', fields=["
        ]

        # Add fields
        for field in fields:
            field_name = field['Field']
            field_type = self._get_form_field_type(field)

        # Build field arguments
        args = []

        # Label
        args.append(f"label='{field_name.title()}'")



        # Format field line
        args_str = ", ".join(args)
        field_line = f"            '{field_name}': {field_type}({args_str}),"
        lines.append(field_line)

        lines.append("        }")
        return "\n".join(lines)

    def _get_form_field_type(self, field: dict) -> str:
        """Helper method to convert database types to Form Field classes"""
        db_type = field['Type'].lower()

        if field['Key'] == 'PRI':
            return 'HiddenField'
        elif 'int' in db_type:
            return 'IntegerField'
        elif 'varchar' in db_type or 'text' in db_type:
            return 'TextField'
        elif 'datetime' in db_type:
            return 'DateTimeField'
        elif 'date' in db_type:
            return 'DateField'
        elif 'decimal' in db_type or 'numeric' in db_type:
            return 'DecimalField'
        elif 'bool' in db_type:
            return 'BooleanField'
        elif 'json' in db_type:
            return 'JsonField'
        else:
            return 'TextField'
