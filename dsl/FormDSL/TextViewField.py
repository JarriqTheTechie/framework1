from framework1.dsl.FormDSL.BaseField import BaseField


class TextViewField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "text_view")
        self.wrapper_class = ""


    def set_wrapper_class(self, class_name: str) -> 'BaseField':
        self.wrapper_class = class_name
        return self

    def render_label(self) -> str:
        help_text_html = f'<small class="help-text {self.field_hidden}">{self.help_text}</small>' if self.help_text else ""
        return f'<label class="{self.label_class} {self.field_hidden}">{self.header}</label>{help_text_html}'

    def render_input(self, value="", record={}) -> str:
        if not self.visible:
            return ""
        readonly_attr = " readonly" if self.readonly else ""
        disabled_attr = " disabled" if self.disabled else ""
        modified_value = self._format_value(value, record)
        return f'{self.render_label()}<div class="{self.wrapper_class}"><input type="{self.field_type}" name="{self.name}" {self.explode_data_attributes()} value="{modified_value}" class="{self.class_name}" style="{self.style}"{readonly_attr}{disabled_attr} {self.hidden} /></div>'
