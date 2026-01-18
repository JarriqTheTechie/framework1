from dataclasses import asdict
from framework1.utilities.DataKlass import DataKlass
from typing import List, Optional

from framework1.dsl.FormDSL.BaseField import BaseField


class FieldGroup:
    def __init__(self, title: str, fields: List[BaseField], description: Optional[str] = None,
                 collapsible: bool = False):
        self.visible = True
        self.title = title
        self.title_class = ""
        self.fields = fields
        self.description = description
        self.description_class = ""
        self.collapsible = collapsible
        self.style = ""
        self.class_name = ""
        self.field_container_class = "field-group"
        self._wrapped_div_id_ = ""
        self._wrapped_div_class_ = ""
        self._is_wrapped_in_div = False

    def set_style(self, style: str) -> 'FieldGroup':
        self.style = style
        return self

    def set_class(self, class_name: str) -> 'FieldGroup':
        self.class_name = class_name
        return self

    def set_field_container_class(self, class_name: str) -> 'FieldGroup':
        self.field_container_class = class_name
        return self

    def set_description_class(self, class_name: str) -> 'FieldGroup':
        self.description_class = class_name
        return self

    def set_title_class(self, class_name: str) -> 'FieldGroup':
        self.title_class = class_name
        return self

    def visible_on(self, boolean: bool) -> 'FieldGroup':
        self.visible = boolean
        return self

    def wrap_in_div_with_class_and_id(self, class_name: str, id="") -> 'FieldGroup':
        self._is_wrapped_in_div = True
        self._wrapped_div_id_ = id
        self._wrapped_div_class_ = class_name
        return self

    def inherit_controller_from(self, parent, field):
        self._stimulus_controller = getattr(parent, "_stimulus_controller", None)
        field.inherit_controller_from(self)
        return self


    def render(self, data: dict, form) -> str:
        try:
            data = asdict(data)
        except AttributeError:
            data = data
        except TypeError:
            data = data
        if not self.visible:
            return ""

        def resolve_dotted(data, dotted_key):
            keys = dotted_key.split(".")
            current = data
            for key in keys:
                if isinstance(current, dict) or isinstance(current, DataKlass):
                    current = current.get(key)
                else:
                    return ""
            return current

        if self._is_wrapped_in_div:
            wrapped_id = self._wrapped_div_id_
            wrapped_class = self._wrapped_div_class_
            wrapper_start = f'<div id="{wrapped_id}" class="{wrapped_class}">'
            wrapper_end = '</div>'
        else:
            wrapper_start = ""
            wrapper_end = ""

        group_html = f'{wrapper_start}<div class="field-group {self.class_name}" style="{self.style}">'
        if self.title != "":
            group_html += f'<div class="row mb-3"><legend class="{self.title_class}">{self.title}</legend></div>'


        if self.description:
            group_html += f'<p class="{self.description_class}">{self.description}</p>'


        for field in self.fields:
            self.inherit_controller_from(form, field)
            raw_value = resolve_dotted(data, field.name)
            formatted_value = field._format_value(raw_value, data)
            group_html += f'<div class="{self.field_container_class} {field.get_outer_class()}">{field.render_input(formatted_value, data)}{form.render_errors(field.name)}</div>'

        group_html += f'</div>{wrapper_end}'
        return group_html

