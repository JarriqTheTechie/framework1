import json
import os
import pathlib
import re
from typing import List


def _write_file(path: pathlib.Path, content: str, overwrite: bool):
    if path.exists() and not overwrite:
        print(f"[skip] {path} already exists. Pass overwrite=True to replace.")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def generate_form(resource_name: str, is_table: bool = False, overwrite: bool = False):
    """
    Generate a form in the lib/handlers/resource/forms folder based on the model
    in the lib/handlers/resource/models folder.
    """
    from framework1.cli.resource_handler import transform_word
    resource = transform_word(resource_name)
    title_singular = resource["title_singular"]
    title_plural = resource["title_plural"]
    slug_singular = resource["slug_singular"]
    slug_plural = resource["slug_plural"]
    pascal_singular = resource["pascal_singular"]
    pascal_plural = resource["pascal_plural"]
    snake_singular = resource["snake_singular"]
    snake_plural = resource["snake_plural"]

    base_path = pathlib.Path("lib/handlers") / snake_plural

    # Paths for models and forms
    models_path = base_path / "models"
    forms_path = base_path / "forms" if not is_table else base_path / "tables"

    # Validate the resource directory structure exists
    if not models_path.exists() or not forms_path.exists():
        print(f"[error] Resource '{resource_name}' does not exist or structure is invalid.")
        return

    # Find the model file
    model_files = list(models_path.glob("*.py"))
    if not model_files:
        print(f"[error] No model found in {models_path}")
        return

    # Using the first model file (files are typically unique per resource)
    model_file = model_files[0]

    # Extract class definition
    with open(model_file, "r") as f:
        model_content = f.read()

    # Extract the model class name
    model_class_match = re.search(r"class (\w+)\(ActiveRecord\):", model_content)
    if not model_class_match:
        print(f"[error] No ActiveRecord class found in {model_file}")
        return
    model_class_name = model_class_match.group(1)

    if not is_table:
        print(f"[ok] Generating form for model: {model_class_name}")
        fields = []
        fields_string = ""
        field_lines = re.findall(r"^\s+(\w+)\s+=\s+(\w+Field.*?)$", model_content, re.MULTILINE)
        for field_name, field_type in field_lines:
            fields.append(f"    {field_name} = {field_type}")
            fields_string += f"""                    TextField('{field_name}').set_label("{field_name.replace("_", " ").title()}").set_class("form-control ps-1"),\n"""

        # Generate the form content
        form_content = f"""from typing import List
from framework1.dsl.FormDSL.TextField import TextField
from framework1.dsl.FormDSL.BaseField import BaseField
from framework1.dsl.FormDSL.FieldGroup import FieldGroup
from framework1.dsl.FormDSL.Form import Form
from typing import Tuple
from framework1.database.ActiveRecord import ActiveRecord
from lib.handlers.{snake_plural}.models.{pascal_singular} import {pascal_singular}


class {pascal_singular}Form(Form):
    def __init__(self, data):
        from lib.handlers.{snake_plural}.{pascal_singular}Controller import {pascal_singular}Controller
        super().__init__(data)
        controller: {pascal_singular}Controller = {pascal_singular}Controller()
        self.set_submit_button_class("btn btn-dark mt-3").set_submit_button_style(
            "border-radius: 0 !important;").set_class("row border-bottom pb-3 border-top pt-3").detect_form_action(data, controller.{pascal_singular}Store, controller.{pascal_singular}Update)

    def validate_and_create(self) -> Tuple[None | ActiveRecord, Form]:
        '''
        Validates the form data and creates a new {pascal_singular} record if valid.
        :return: Tuple containing the created resource or None, and the form instance.
        '''
        if self.validate():
            resource = {pascal_singular}().create(**self.data)
            return resource, self
        return None, self    
        
    def validate_and_update(self, id: str | int) -> Tuple[None | ActiveRecord, Form]:
        '''
        Validates the form data and updates an existing {pascal_singular} record if valid.
        :return: Tuple containing the updated resource or None, and the form instance.
        '''
        if self.validate():
            resource = {pascal_singular}().find(id).update(**self.data)
            return resource, self
        return None, self  

    def schema(self) -> List[BaseField| FieldGroup]:
        return [
            FieldGroup(
                "{pascal_singular} Information",
                fields=[
                    {fields_string}
                ]
            ).set_field_container_class("col-3 mb-3").set_title_class("h6 fw-bold ps-0")
            .set_class("col-lg-12 row"),
        ]
    """

        # Save the form
        form_file_path = forms_path / f"{pascal_singular}Form.py"
        if _write_file(form_file_path, form_content, overwrite):
            print(f"[ok] Form generated: {form_file_path}")
    else:
        print(f"[ok] Generating table for model: {model_class_name}")
        fields = []
        fields_string = ""
        field_lines = re.findall(r"^\s+(\w+)\s+=\s+(\w+Field.*?)$", model_content, re.MULTILINE)
        for field_name, field_type in field_lines:
            fields.append(f"    {field_name} = {field_type}")
            fields_string += f"""                    TextColumn('{field_name}').label("{field_name.replace("_", " ").title()}"),\n"""

        # Generate the form content
            # Generate    table
        table_content = f'''from framework1.dsl.Table import Table, TextColumn
from lib.handlers.{snake_plural}.models.{pascal_singular} import {pascal_singular}

class {pascal_singular}Table(Table):
    model = {pascal_singular}
    table_class = "table fs-9 mb-0"

    def schema(self):
        return [
            {fields_string}            
        ]
        
    def record_url(self, data):
        return f"window.location.href = '/{slug_plural}/{{data.get('id')}}'"


                '''

        table_path = pathlib.Path(base_path) / "tables" / f"{pascal_singular}Table.py"
        if _write_file(table_path, table_content, overwrite):
            print(f"[ok] Table generated: {table_path}")

#########################################################################

        print(f"✨ Generating infolist for model: {model_class_name}")
        fields = []
        fields_string = ""
        field_lines = re.findall(r"^\s+(\w+)\s+=\s+(\w+Field.*?)$", model_content, re.MULTILINE)
        for field_name, field_type in field_lines:
            fields.append(f"    {field_name} = {field_type}")
            fields_string += f"""                    InfoListField('{field_name}').label("{field_name.replace("_", " ").title()}"),\n"""

        # Generate the form content
            # Generate    table
        infolist_content = f'''from framework1.dsl.InfoList import InfoList, InfoListField
        
class {pascal_singular}InfoList(InfoList):
    def schema(self):
        return [
            {fields_string}            
        ]


                '''

        infolsit_path = pathlib.Path(base_path) / "infolists" / f"{pascal_singular}InfoList.py"
        if _write_file(infolsit_path, infolist_content, overwrite):
            print(f"[ok] Infolist generated: {infolsit_path}")

