from typing import Tuple, Union, List, Self, Dict

from framework1.dsl.FormDSL.BaseField import BaseField

def fix_inline_js_quotes(js: str) -> str:
    """
    Fix broken inline JS caused by double quotes inside HTML attributes.
    Ensures inner JS strings use single quotes.
    """
    # Replace any double-quoted JS string with single quotes
    return re.sub(r'"([^"]*?)"', r"'\1'", js)

class SelectField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "select")
        self.options: List[Union[str, Tuple[str, str], Dict[str, str]]] = []

    def set_options(self, options: Union[List[str], List[Tuple[str, str]], List[Dict[str, str]]]) -> Self:
        self.options = options
        return self

    def render_input(self, value="", record={}) -> str:
        if not self.visible:
            return ""
        disabled_attr = " disabled" if self.disabled else ""

        # Generate HTML for options and optgroups
        options_html = ""
        for html in self._generate_option_html(self.options, value):
            options_html += html

        if callable(self.help_text):
            help_text = self.help_text(record, value)
        else:
            help_text = self.help_text if self.help_text else ""

        return f"""
        {self.render_label(value, record) if self.label_position == "above" else ""}
        <select name="{self.name}" 
                class="{self.class_name}" 
                {self.explode_data_attributes()} 
                {disabled_attr}>
            {options_html}
        </select>
        {self.render_label(value, record) if self.label_position == "below" else ""}
        {f"<script>{self.script}</script>" if self.script else ""}
        """
    def _generate_option_html(self, options, selected_value):
        for option in options:
            if isinstance(option, str):
                yield f'<option value="{option}" {"selected" if option == selected_value else ""}>{option}</option>'

            elif isinstance(option, tuple):
                val, lbl = option
                yield f'<option value="{val}" {"selected" if val == selected_value else ""}>{lbl}</option>'

            elif isinstance(option, dict):
                if "group" in option and "options" in option:
                    group_label = option["group"]
                    group_options = option["options"]
                    group_html = f'<optgroup label="{group_label}">'
                    for sub in group_options:
                        val = sub.get("value")
                        lbl = sub.get("label", val)
                        selected = "selected" if val == selected_value else ""
                        group_html += f'<option value="{val}" {selected}>{lbl}</option>'
                    group_html += "</optgroup>"
                    yield group_html
                else:
                    for val, lbl in option.items():
                        yield f'<option value="{val}" {"selected" if val == selected_value else ""}>{lbl}</option>'
