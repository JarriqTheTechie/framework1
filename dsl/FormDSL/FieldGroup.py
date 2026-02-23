from dataclasses import asdict
import html
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
        # layout helpers
        self.row_class = "row"
        self.columns: List[str] = []
        self._even_columns_count: int | None = None
        self._even_columns_breakpoint = "md"

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

    def set_row_class(self, class_name: str) -> 'FieldGroup':
        """Set the row wrapper class used when rendering columns."""
        self.row_class = class_name
        return self

    def set_columns(self, columns: List[str]) -> 'FieldGroup':
        """Explicit column classes applied per field (loops if fewer than fields)."""
        self.columns = columns
        return self

    def set_even_columns(self, count: int, breakpoint: str = "md") -> 'FieldGroup':
        """
        Auto-distribute fields into even columns using Bootstrap-style col-{bp}-{span}.
        Example: count=2 -> col-md-6, count=3 -> col-md-4.
        """
        self._even_columns_count = count
        self._even_columns_breakpoint = breakpoint
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
            wrapped_id = html.escape(self._wrapped_div_id_)
            wrapped_class = html.escape(self._wrapped_div_class_)
            wrapper_start = f'<div id="{wrapped_id}" class="{wrapped_class}">'
            wrapper_end = '</div>'
        else:
            wrapper_start = ""
            wrapper_end = ""

        group_html = f'{wrapper_start}<div class="field-group {html.escape(self.class_name)}" style="{html.escape(self.style)}">'
        if self.title != "":
            group_html += f'<div class="row mb-3"><legend class="{html.escape(self.title_class)}">{html.escape(self.title)}</legend></div>'


        if self.description:
            group_html += f'<p class="{html.escape(self.description_class)}">{html.escape(self.description)}</p>'


        use_columns = bool(self.columns) or self._even_columns_count
        if use_columns:
            group_html += f'<div class="{html.escape(self.row_class)}">'

        for idx, field in enumerate(self.fields):
            if self.columns:
                col_class = self.columns[idx % len(self.columns)]
            elif self._even_columns_count:
                # Guard divide-by-zero
                span = max(1, round(12 / max(1, self._even_columns_count)))
                col_class = f"col-{self._even_columns_breakpoint}-{span}"
            else:
                col_class = ""

            raw_value = resolve_dotted(data, field.name)
            formatted_value = field._format_value(raw_value, data)
            container_classes = f"{col_class} {self.field_container_class} {field.get_outer_class()}".strip()
            group_html += f'<div class="{html.escape(container_classes)}">{field.render_input(formatted_value, data)}{form.render_errors(field.name)}</div>'

        if use_columns:
            group_html += "</div>"

        group_html += f'</div>{wrapper_end}'
        return group_html

