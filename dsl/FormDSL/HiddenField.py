import html

from framework1.dsl.FormDSL.BaseField import BaseField


class HiddenField(BaseField):
    """Hidden input that suppresses labels/help text."""

    def __init__(self, name: str):
        super().__init__(name, "hidden")

    def render_input(self, value="", record={}) -> str:
        modified_value = html.escape(str(self._format_value(value, record)))
        escaped_name = html.escape(self.name)
        return f'<input type="hidden" name="{escaped_name}" id="{escaped_name}" value="{modified_value}" {self.explode_data_attributes()} />'
