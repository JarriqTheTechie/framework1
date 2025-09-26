from typing import Tuple, Union, List, Self, Dict

from framework1.dsl.FormDSL.BaseField import BaseField


class CheckboxField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "checkbox")
        self.options: List[Union[str, Tuple[str, str], Dict[str, str]]] = []
        self.outer_class = "form-check"

    def set_options(self, options: Union[List[str], List[Tuple[str, str]], List[Dict[str, str]]]) -> Self:
        self.options = options
        return self

    def set_outer_class(self, outer_class: str) -> Self:
        self.outer_class = outer_class
        return self

    def render_input(self, value="") -> str:
        if not self.visible:
            return ""

        disabled_attr = " disabled" if self.disabled else ""
        value_set = set(value if isinstance(value, list) else [value])

        checkboxes_html = "".join(
            f'''
            <div class="{self.outer_class}">
                <input class="form-check-input {self.class_name}" type="checkbox" 
                       name="{self.name}[]" id="{self.name}_{i}" value="{val}" 
                       {"checked" if val in value_set else ""} {self.explode_data_attributes()}{disabled_attr}>
                <label class="form-check-label" for="{self.name}_{i}">{lbl}</label>
            </div>
            '''
            for i, (val, lbl) in enumerate(self._generate_option_html(self.options))
        )

        return f'{self.render_label()}{checkboxes_html}'

    def _generate_option_html(self, options):
        for option in options:
            if isinstance(option, str):
                yield option, option
            elif isinstance(option, tuple):
                yield option
            elif isinstance(option, dict):
                for key, label in option.items():
                    yield key, label
