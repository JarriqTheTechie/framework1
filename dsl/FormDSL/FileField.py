import html
from framework1.dsl.FormDSL.BaseField import BaseField


class FileField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "file")
        self.accept_types: str | None = None
        self.multiple: bool = False

    def set_field_type(self, field_type: str) -> 'FileField':
        self.field_type = field_type
        return self

    def set_accept(self, mime_types: str) -> 'FileField':
        """
        Comma-separated list of MIME types or extensions, e.g. 'image/*,.pdf'.
        """
        self.accept_types = mime_types
        return self

    def allow_multiple(self, multiple: bool = True) -> 'FileField':
        self.multiple = multiple
        return self

    def render_input(self, value="", record={}) -> str:
        readonly_attr = " readonly" if self.readonly else ""
        disabled_attr = " disabled" if self.disabled else ""
        multiple_attr = " multiple" if self.multiple else ""
        accept_attr = f' accept="{self.accept_types}"' if self.accept_types else ""
        escaped_name = html.escape(self.name)
        escaped_class = html.escape(self.class_name)
        escaped_style = html.escape(self.style)
        hidden_attr = html.escape(self.hidden)
        return f"""
        {self.render_label(record, value) if self.label_position == "above" else ""}
        <input type="{self.field_type}"
               id="{escaped_name}"
               name="{escaped_name if not self.multiple else escaped_name + '[]'}"
               {self.explode_data_attributes()}
               class="{escaped_class}"
               style="{escaped_style}"
               {readonly_attr}{disabled_attr}{multiple_attr}{accept_attr} {hidden_attr}/>
        {self.render_label(record, value) if self.label_position == "below" else ""}
        {self.render_help_text(record, value) if self.help_text and self.help_text_position == "below" else ""}
        """
