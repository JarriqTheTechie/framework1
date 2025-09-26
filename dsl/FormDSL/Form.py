from framework1.utilities.DataKlass import DataKlass
from typing import Self, Union, Callable, List, Dict, Tuple, Optional, Any

from flask import Response
from markupsafe import Markup

from framework1.dsl.FormDSL.BaseField import BaseField
from framework1.dsl.FormDSL.FieldGroup import FieldGroup


class Form:
    def __init__(self, data: dict | DataKlass):
        self.submit_button_style = ""
        self.visible = True
        self.enctype = ""
        self.data = data
        self.errors: Dict[str, List[str]] = {}
        self.class_name = ""
        self.submit_button_text = "Submit"
        self.submit_button_class = ""
        self.method = "POST"
        self.action = ""
        self.style = ""

    def get_create_button_text(self) -> str:
        """Override this method to customize create button text."""
        return "Create"

    def get_update_button_text(self) -> str:
        """Override this method to customize update button text."""
        return "Update"

    def get_id_key(self) -> str:
        """Override this method to customize the key used for ID detection."""
        return "id"

    def detect_form_action(self, data: dict[str, Any], store_action: Callable, update_action: Callable) -> 'Form':
        """
        Simple helper to set appropriate form action based on data.

        Args:
            data: Form data dictionary
            store_action: Create/Store action method
            update_action: Edit/Update action method
        """
        id_key = self.get_id_key()
        if data and id_key in data and data[id_key]:
            self.set_submit_button_text(self.get_update_button_text())
            # self.set_form_action(update_action, **{id_key: data[id]})
            self.set_form_action(update_action, **{"id": data[id_key]})
        else:
            self.set_submit_button_text(self.get_create_button_text())
            self.set_form_action(store_action)
        return self

    def set_method(self, method: str) -> 'Form':
        self.method = method
        return self

    def set_class(self, class_name: str) -> 'Form':
        self.class_name = class_name
        return self

    def set_style(self, style: str) -> 'Form':
        """Sets inline CSS style for the form."""
        self.style = style
        return self

    def set_submit_button_text(self, text: str) -> 'Form':
        self.submit_button_text = text
        return self

    def set_submit_button_class(self, class_name: str) -> 'Form':
        self.submit_button_class = class_name
        return self

    def set_submit_button_style(self, style: str) -> 'Form':
        self.submit_button_style = style
        return self

    def set_form_action(self, action: str | Response | Callable, **kwargs) -> 'Form':
        if isinstance(action, (Response, Callable)):
            from flask import url_for
            self.action = url_for(action.__name__, **kwargs)
        else:
            self.action = action
        return self

    def schema(self) -> List[BaseField| FieldGroup]:
        """Override this method to define schema."""
        return []

    def validate(self) -> bool:
        """Validate all fields in the form and collect errors."""
        self.errors.clear()
        valid = True
        for item in self.schema():
            if isinstance(item, FieldGroup):
                # Validate each field in the FieldGroup
                for field in item.fields:
                    value = self.data.get(field.name, "")
                    field_errors = field.validate(value)
                    if field_errors:
                        self.errors[field.name] = field_errors
                        valid = False
            else:
                # Validate individual BaseField directly
                value = self.data.get(item.name, "")
                field_errors = item.validate(value)
                if field_errors:
                    self.errors[item.name] = field_errors
                    valid = False
        return valid

    def render_errors(self, field_name) -> str:

        if field_name in self.errors:
            error_html = "".join(f'<p class="error">{error}</p>' for error in self.errors[field_name])
            return f'<div class="error-messages">{error_html}</div>'
        return ""

    def visible_on(self, boolean: bool) -> 'Form':
        """Set the visibility of the form."""
        self.visible = boolean
        return self


    def set_enctype(self, enctype: str) -> 'Form':
        self.enctype = enctype
        return self

    def set_data(self, data: dict) -> 'Form':
        self.data = data
        return self

    def render(self) -> Markup | str:
        if self.visible:
            html = f'<form action="{self.action}" method="{self.method}" class="{self.class_name}" id="{self.__class__.__name__}" style="{self.style}" enctype="{self.enctype}">\n'
            outer_class = "form-group"

            loop_counter = 1
            loop_length = 1 #len(self.schema())
            for item in self.schema():
                if isinstance(item, FieldGroup):
                    item.form = self
                    html += item.render(self.data, self)
                    if loop_counter == loop_length:
                        pass
                else:
                    value = self.data.get(item.name, "")
                    if self.field_type == "checkbox":
                        outer_class = "form-check"

                    html += f'  <div class="{outer_class}">{item.render_input(value, item)}{self.render_errors(item.name)}</div>\n'
                loop_counter += 1
            html += f'<div style="width: 100%"><button class="{self.submit_button_class}" type="submit" id="{self.__class__.__name__}_btn" style="{self.submit_button_style}">{self.submit_button_text or "Submit"}</button></div>'
            html += f'\n</form>'
        else:
            html = ""
        return Markup(html)


    def __str__(self) -> str:
        return self.render()
