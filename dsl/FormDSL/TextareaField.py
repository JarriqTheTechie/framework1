from framework1.dsl.FormDSL.BaseField import BaseField


class TextareaField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "textarea")
        self.rows = 4


    def set_rows(self, row_count):
        self.rows = row_count
        return self


    def render_label(self) -> str:
        help_text_html = f'<small class="help-text">{self.help_text}</small>' if self.help_text else ""
        return f'<label class="{self.label_class}">{self.header}</label>{help_text_html}'

    def render_input(self, value="", record={}) -> str:
        modified_value = self._format_value(value, record)
        if not self.visible:
            return ""
        readonly_attr = " readonly" if self.readonly else ""
        disabled_attr = " disabled" if self.disabled else ""
        return f'{self.render_label()}<{self.field_type} name="{self.name}" class="{self.class_name}" rows="{self.rows}" {self.explode_data_attributes()} style="{self.style}"{readonly_attr}{disabled_attr}>{modified_value}</textarea>'

