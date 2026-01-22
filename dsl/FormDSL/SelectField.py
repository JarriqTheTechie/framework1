from typing import Tuple, Union, List, Self, Dict, Any
import json
import html
import re
from framework1.dsl.FormDSL.BaseField import BaseField


def _normalize_for_compare(value: Any) -> str:
    """
    Normalize any supported value type (str, tuple, dict, list) into a
    string representation for consistent comparison and HTML rendering.
    """
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def fix_inline_js_quotes(js: str) -> str:
    """
    Fix broken inline JS caused by double quotes inside HTML attributes.
    Ensures inner JS strings use single quotes.
    """
    return re.sub(r'"([^"]*?)"', r"'\1'", js)


class SelectField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "select")
        self.options: List[Union[str, Tuple[str, str], Dict[str, Any]]] = []

    def set_options(
        self,
        options: Union[List[str], List[Tuple[str, str]], List[Dict[str, Any]]]
    ) -> Self:
        self.options = options
        return self

    def render_input(self, value: Any = "", record: Dict[str, Any] = {}) -> str:
        if not self.visible:
            return ""
        disabled_attr = " disabled" if self.disabled else ""
        multiple_attr = ' multiple="multiple"' if str(self.name).endswith("[]") else ""

        # Generate HTML for options and optgroups
        options_html = "".join(self._generate_option_html(self.options, value))

        if callable(self.help_text):
            help_text = self.help_text(record, value)
        else:
            help_text = self.help_text if self.help_text else ""

        return f"""
        {self.render_label(value, record) if self.label_position == "above" else ""}
        <select name="{self.name}" 
                class="{self.class_name}" 
                {self.explode_data_attributes()} 
                {disabled_attr}{multiple_attr}>
            {options_html}
        </select>
        {self.render_label(value, record) if self.label_position == "below" else ""}
        {f"<script>{self.script}</script>" if self.script else ""}
        """

    def _generate_option_html(self, options, selected_value):
        # Support single values and list-like selections
        selected_set = set()
        if isinstance(selected_value, (list, tuple, set)):
            selected_set = {_normalize_for_compare(v) for v in selected_value}
            normalized_selected = None
        else:
            normalized_selected = _normalize_for_compare(selected_value)

        for option in options:
            # Plain string
            if isinstance(option, str):
                val_str = _normalize_for_compare(option)
                selected = "selected" if val_str == normalized_selected or val_str in selected_set else ""
                yield f'<option value="{html.escape(val_str)}" {selected}>{option}</option>'

            # Tuple (value, label)
            elif isinstance(option, tuple):
                val, lbl = option
                val_str = _normalize_for_compare(val)
                selected = "selected" if val_str == normalized_selected or val_str in selected_set else ""
                yield f'<option value="{html.escape(val_str)}" {selected}>{lbl}</option>'

            # Dict (could be group or simple map)
            elif isinstance(option, dict):
                if "group" in option and "options" in option:
                    group_html = f'<optgroup label="{option["group"]}">'
                    for sub in option["options"]:
                        val = sub.get("value")
                        lbl = sub.get("label", val)
                        val_str = _normalize_for_compare(val)
                        selected = "selected" if val_str == normalized_selected or val_str in selected_set else ""
                        group_html += f'<option value="{html.escape(val_str)}" {selected}>{lbl}</option>'
                    group_html += "</optgroup>"
                    yield group_html
                else:
                    for val, lbl in option.items():
                        val_str = _normalize_for_compare(val)
                        selected = "selected" if val_str == normalized_selected or val_str in selected_set else ""
                        yield f'<option value="{html.escape(val_str)}" {selected}>{lbl}</option>'

