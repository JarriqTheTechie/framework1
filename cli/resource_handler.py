import os


from flask import redirect
import re
import inflect
from slugify import slugify

from framework1.database.ActiveRecord import ActiveRecord

# Initialize the inflect engine
p = inflect.engine()


def split_camel_case(word: str) -> str:
    """Split PascalCase or camelCase into space-separated words."""
    return re.sub(r'(?<!^)(?=[A-Z])', ' ', word)


def to_pascal_case(phrase: str) -> str:
    return ''.join(word.capitalize() for word in phrase.split())


def to_snake_case(phrase: str) -> str:
    return '_'.join(word.lower() for word in phrase.split())


def transform_word(raw_word: str):
    spaced = split_camel_case(raw_word)  # e.g. "Destruction Log"
    plural_spaced = p.plural(spaced.lower())  # e.g. "Destruction Logs"

    return {
        "title_singular": spaced.title(),  # Destruction Log
        "title_plural": plural_spaced.title(),  # Destruction Logs
        "slug_singular": slugify(spaced),  # destruction-log
        "slug_plural": slugify(plural_spaced),  # destruction-logs
        "pascal_singular": to_pascal_case(spaced),  # DestructionLog
        "pascal_plural": to_pascal_case(plural_spaced),  # DestructionLogs
        "snake_singular": to_snake_case(spaced),  # destruction_log
        "snake_plural": to_snake_case(plural_spaced),  # destruction_logs
    }


def parse_field_definition(field_str: str) -> dict:
    """Parse a field definition string in format name:type:args into a dictionary.

    Example: "name:CharField:max_length=100,required=true"
    """
    parts = field_str.split(':')
    if len(parts) < 2:
        raise ValueError(f"Invalid field definition: {field_str}. Format should be name:type[:args]")

    field = {
        'name': parts[0],
        'type': parts[1],
        'label': parts[0].replace('_', ' ').title()
    }

    if len(parts) > 2:
        args = parts[2].split(',')
        for arg in args:
            if '=' in arg:
                key, value = arg.split('=')
                if value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                elif value.isdigit():
                    value = int(value)
                field[key] = value
            else:
                field[arg] = True

    return field


def create_resource_handler(resource_name: str, database: str = None, field_definitions: list[str] = None):
    resource = transform_word(resource_name)
    title_singular = resource["title_singular"]
    title_plural = resource["title_plural"]
    slug_singular = resource["slug_singular"]
    slug_plural = resource["slug_plural"]
    pascal_singular = resource["pascal_singular"]
    pascal_plural = resource["pascal_plural"]
    snake_singular = resource["snake_singular"]
    snake_plural = resource["snake_plural"]

    fields = []
    if field_definitions:
        fields = [parse_field_definition(field_str) for field_str in field_definitions]

    model_fields = []  # Use a list instead of string concatenation
    form_fields = []
    table_fields = []
    infolsit_fields = []
    for field in fields:
        field_name = field['name']
        field_type = field['type']
        field_args = []
        for k, v in field.items():
            if k not in ['name', 'type', 'label']:
                # Handle string values by adding quotes
                if isinstance(v, str):
                    field_args.append(f"{k}='{v}'")
                else:
                    field_args.append(f"{k}={v}")

        model_field_definition = f"    {field_name} = {field_type}({', '.join(field_args)})"
        form_field_definition = f"                    TextField('{field_name}').set_label('{field_name.title()}').set_class('form-control ps-1'),"
        table_field_definition = f"            TextColumn('{field_name}').label('{field_name.title()}'),"
        infolist_field_definition = f"            InfoListField('{field_name}').label('{field_name.title()}'),"
        model_fields.append(model_field_definition)
        form_fields.append(form_field_definition)
        table_fields.append(table_field_definition)
        infolsit_fields.append(infolist_field_definition)

    # Join all fields with newlines
    model_fields = "\n".join(model_fields)
    form_fields = "\n".join(form_fields)
    table_fields = "\n".join(table_fields)
    infolsit_fields = "\n".join(infolsit_fields)
    #raise Exception(f"Model fields: {model_fields}")



    base_path = os.path.join("lib", "handlers", snake_plural)
    subfolders = ["tables", "templates", "forms", "styles", "scripts", "models", "infolists"]

    # Create the base structure
    os.makedirs(base_path, exist_ok=True)
    for subfolder in subfolders:
        subfolder_path = os.path.join(base_path, subfolder)
        os.makedirs(subfolder_path, exist_ok=True)

        # Generate index.html template
        if subfolder == "templates":
            template_content = f'''{{% extends 'base.html' %}}
{{% block content %}}

    <div class="container-fluid px-0 mb-3" id="resource-action-panel">
        <a name="" id="" class="btn btn-dark ml-0" href="{{{{ url_for('{pascal_singular}Create') }}}}" role="button">Create {title_singular}</a>
    </div>

    <div class="mx-n4 px-4 mx-lg-n6 px-lg-6 bg-body-emphasis border-top border-bottom border-translucent position-relative top-1">
        <div class="table-responsive scrollbar mx-n1 px-1">
            {{{{ table|safe }}}}
        </div>
    </div>


{{% endblock %}}
'''
            with open(os.path.join(subfolder_path, "index.html"), "w") as f:
                f.write(template_content)

        # Generate create.html template
            template_content = '''{% extends 'base.html' %}
{% block content %}

    
    {{ form|safe }}

{% endblock %}
'''
            with open(os.path.join(subfolder_path, "create.html"), "w") as f:
                f.write(template_content)

            # Generate edit.html template
            template_content = '''{% extends 'base.html' %}
{% block content %}

    
    {{ form|safe }}

{% endblock %}
'''
            with open(os.path.join(subfolder_path, "edit.html"), "w") as f:
                f.write(template_content)

            # Generate details.html template
            template_content = '''{% extends 'base.html' %}
{% block content %}

    
    {{ form|safe }}

{% endblock %}
'''
            with open(os.path.join(subfolder_path, "details.html"), "w") as f:
                f.write(template_content)

    # Generate model
    model_content = f'''from framework1.database.ActiveRecord import ActiveRecord
from framework1.database.fields.Fields import IntegerField, CharField, DateTimeField
from framework1.database.active_record.utils.decorators import on
from lib.services.{database} import {database}

class {pascal_singular}(ActiveRecord):
    __table__ = "{snake_plural}"
    __driver__ = "mysql"
    __database__ = {database}
    __primary_key__ = "id"

    id = IntegerField(primary_key=True, auto_increment=True)
{model_fields}


if __name__ == "__main__":
    {pascal_singular}.create_table()  # This will create the table directly
'''

    model_path = os.path.join(base_path, "models", f"{pascal_singular}.py")
    with open(model_path, "w") as f:
        f.write(model_content)


    # Generate    form
    form_content = f'''from typing import List

from framework1.dsl.FormDSL.BaseField import BaseField
from framework1.dsl.FormDSL.DateField import DateField
from framework1.dsl.FormDSL.FieldGroup import FieldGroup
from framework1.dsl.FormDSL.Form import Form
from framework1.dsl.FormDSL.SelectField import SelectField
from framework1.dsl.FormDSL.TextField import TextField
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
        """
        Validates the form data and creates a new {pascal_singular} record if valid.
        :return: Tuple containing the created resource or None, and the form instance.
        """
        if self.validate():
            resource = {pascal_singular}().create(**self.data)
            return resource, self
        return None, self    
        
    def validate_and_update(self, id: str | int) -> Tuple[None | ActiveRecord, Form]:
        """
        Validates the form data and updates an existing {pascal_singular} record if valid.
        :return: Tuple containing the updated resource or None, and the form instance.
        """
        if self.validate():
            resource = {pascal_singular}().find(id).update(**self.data)
            return resource, self
        return None, self                 

    def schema(self) -> List[BaseField | FieldGroup]:
        return [
            FieldGroup(
                "{title_singular} Information",
                fields=[
{form_fields}                    
                ]
            ).set_field_container_class("col-6 mb-3").set_title_class("h6 fw-bold ps-0")
            .set_class("col-lg-6 px-4 mt-3 row"),
        ]


    '''

    form_path = os.path.join(base_path, "forms", f"{pascal_singular}Form.py")
    with open(form_path, "w") as f:
        f.write(form_content)


        # Generate    table
        table_content = f'''from framework1.dsl.Table import Table, TextColumn
from lib.handlers.{snake_plural}.models.{pascal_singular} import {pascal_singular}

class {pascal_singular}Table(Table):
    model = {pascal_singular}
    table_class = "table table-striped table-hover mt-3"

    def schema(self):
        return [
            TextColumn('id'),
{table_fields}            
        ]
        
    def record_url(self, data):
        return f"window.location.href = '/{slug_plural}/{{data.get('id')}}'"


        '''

        table_path = os.path.join(base_path, "tables", f"{pascal_singular}Table.py")
        with open(table_path, "w") as f:
            f.write(table_content)

            # Generate    InfoList
            infolist_content = f'''from framework1.dsl.InfoList import InfoList, InfoListField

class {pascal_singular}InfoList(InfoList):
    def schema(self):
        return [
            InfoListField('id'),
{infolsit_fields}            
        ]


            '''

            infolist_path = os.path.join(base_path, "infolists", f"{pascal_singular}InfoList.py")
            with open(infolist_path, "w") as f:
                f.write(infolist_content)


    # Generate controller
    route_path = resource_name.lower().replace('_', '-')
    if not route_path.endswith('s'):
        route_path += 's'

    controller_content = f'''from app import app
from flask import render_template, abort
from framework1.core_services.Request import Request
from framework1.core_services.ViewProps import ViewProps
from framework1.service_container._Injector import injectable_route
from lib.handlers.{snake_plural}.forms.{pascal_singular}Form import {pascal_singular}Form
from lib.handlers.{snake_plural}.tables.{pascal_singular}Table import {pascal_singular}Table
from lib.handlers.{snake_plural}.models.{pascal_singular} import {pascal_singular}
from flask import redirect, url_for

class {pascal_singular}Controller:
    def __init__(self):
        pass
    
    def GetNavigation(self):
        return [
            dict(
                title="{title_plural}",
                url=url_for('{pascal_singular}Index'),
                icon="ri-question-line",
                weight=0,
                visible=True,
                group=None,
                group_icon=None,
            )
        ]

    @injectable_route(app, '/{slug_plural}', methods=['GET'])
    def {pascal_singular}Index(self, view_props: ViewProps, request: Request):
        page_title = "{title_plural}"
        table = {pascal_singular}Table().paginate(per_page=10)
        return render_template('{snake_plural}/templates/index.html', **view_props.compact())

    @injectable_route(app, '/{slug_plural}/<id>', methods=['GET'])
    def {pascal_singular}Details(self, id: int,view_props: ViewProps, request: Request):
        page_title = "{title_singular} Details"
        resource = {pascal_singular}().find(id)
        form = {pascal_singular}Form(resource.to_dict())
        return render_template('{snake_plural}/templates/details.html', **view_props.compact())                

    @injectable_route(app, '/{slug_plural}/create', methods=['GET'])
    def {pascal_singular}Create(self, view_props: ViewProps, request: Request):
        page_title = "Create {title_singular}"
        form = {pascal_singular}Form(request.all())
        return render_template('{snake_plural}/templates/create.html', **view_props.compact())

    @injectable_route(app, '/{route_path}/create', methods=['POST'])
    def {pascal_singular}Store(self, view_props: ViewProps, request: Request):
        page_title = "Create {title_singular}"
        resource, form = {pascal_singular}Form(request.all()).validate_and_create()
        if not resource:
            return render_template('{snake_plural}/templates/create.html', **view_props.compact())
        return redirect(url_for('{pascal_singular}Details', id=resource.id))
            
    @injectable_route(app, '/{slug_plural}/<id>/update', methods=['GET'])
    def {pascal_singular}Edit(self, view_props: ViewProps, request: Request):
        page_title = "Edit {resource_name.replace('_', ' ').title()}"
        form = {pascal_singular}Form(request.all())
        return render_template('{snake_plural}/templates/edit.html', **view_props.compact())

    @injectable_route(app, '/{slug_plural}/<id>/update', methods=['POST'])
    def {pascal_singular}Update(self, id: int,view_props: ViewProps, request: Request):
        page_title = "Edit {title_singular}"
        resource, form = {pascal_singular}Form(request.all()).validate_and_update(id)
        if not resource:
            return render_template('{snake_plural}/templates/edit.html', **view_props.compact())
        return redirect(url_for('{pascal_singular}Details', id=resource.id))
'''

    controller_path = os.path.join(base_path, f"{pascal_singular}Controller.py")
    with open(controller_path, "w") as f:
        f.write(controller_content)

    print(f"✨ Created resource handler: {base_path}")
    print(f"✨ Generated template: {os.path.join(base_path, 'templates', 'index.html')}")
    print(f"✨ Generated model: {model_path}")
    print(f"✨ Generated controller: {controller_path}")
    print(f"✨ Generated form: {form_path}")
    print(f"✨ Generated table: {table_path}")
    print(f"✨ Generated infolist: {infolist_path}")
