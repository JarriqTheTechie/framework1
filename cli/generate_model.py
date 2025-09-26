import os
from typing import List, Dict, Any

def generate_model(name: str, fields: List[Dict[str, Any]], output_dir: str = "lib/models") -> None:
    """Generate a new model class file"""
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Prepare imports
    field_types = set()
    for field in fields:
        field_types.add(field['type'])

    # Generate model code
    model_code = f'''from framework1.database.ActiveRecord import ActiveRecord
from framework1.database.fields.Fields import {", ".join(field_types)}


class {name.title()}(ActiveRecord):
    __table__ = "{name.lower()}s"
    __driver__ = "mysql"
    __database__ = "CHOOSE_YOUR_DATABASE_HERE"  # Replace with your actual database service
    __primary_key__ = "id"

'''

    # Add fields
    for field in fields:
        field_args = []
        if field.get('primary_key'):
            field_args.append('primary_key=True')
        if field.get('nullable') is not None:
            field_args.append(f'nullable={field["nullable"]}')
        if field.get('max_length'):
            field_args.append(f'max_length={field["max_length"]}')
        if field.get('default'):
            field_args.append(f'default="{field["default"]}"')

        args_str = ", ".join(field_args)
        model_code += f"    {field['name']} = {field['type']}({args_str})\n"

    # Add create_table call
    model_code += f'''

if __name__ == "__main__":
    {name.title()}.create_table()  # This will create the table directly
'''

    # Write to file
    file_path = os.path.join(output_dir, f"{name.title()}.py")
    with open(file_path, "w") as f:
        f.write(model_code)

    print(f"✨ Generated model {name.title()} in {file_path}")
