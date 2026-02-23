from typing import Tuple, Union, List, Self, Dict
import html

from framework1.dsl.FormDSL.BaseField import BaseField


class RadioField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "radio")
        self.options: List[Union[str, Tuple[str, str], Dict[str, str]]] = []
        self.outer_class = ""  # base form-check is applied automatically
        self.inline = False
        self.option_descriptions: Dict[str, str] = {}
        self.disabled_options: set[str] = set()

    def set_options(self, options: Union[List[str], List[Tuple[str, str]], List[Dict[str, str]]]) -> Self:
        self.options = options
        return self

    def set_inline(self, inline: bool = True) -> Self:
        """Render radio buttons inline (adds form-check-inline)."""
        self.inline = inline
        if inline and "col-12" not in self.label_class.split():
            # Ensure label spans full width above inline radios
            self.label_class = (self.label_class + " col-12").strip()
        return self

    def descriptions(self, descriptions: Dict[str, str]) -> Self:
        """Set per-option descriptions keyed by option value."""
        self.option_descriptions = descriptions
        return self

    def disable_options(self, values: List[str]) -> Self:
        """Mark specific options as disabled."""
        self.disabled_options = set(str(v) for v in values)
        return self

    def boolean(self, yes_label="Yes", no_label="No") -> Self:
        """
        Convenience for yes/no radios. Accepts varied truthy/falsey tokens and
        normalizes option values to capitalized 'Yes'/'No' so descriptions can match on either labels or canonical values.
        """
        self.options = [("Yes", yes_label), ("No", no_label)]
        return self

    @staticmethod
    def _normalize_bool_token(token) -> str:
        """
        Normalize common truthy/falsey tokens to 'Yes' or 'No'.
        Supports: True/False, 1/0, '1'/'0', 'yes'/'no' (any case), 'y'/'n', 'true'/'false'.
        """
        truthy = {"1", "true", "t", "yes", "y", "on"}
        falsey = {"0", "false", "f", "no", "n", "off"}
        if isinstance(token, bool):
            return "Yes" if token else "No"
        token_str = str(token).strip().lower()
        if token_str in truthy:
            return "Yes"
        if token_str in falsey:
            return "No"
        # fallback: return original string capitalized
        return token_str.capitalize()

    def set_outer_class(self, outer_class: str) -> Self:
        self.outer_class = outer_class
        return self

    def render_input(self, value="", record={}) -> str:
        if not self.visible:
            return ""

        disabled_attr = " disabled" if self.disabled else ""
        if isinstance(value, list):
            value_set = {self._normalize_bool_token(v) for v in value}
        else:
            value_set = {self._normalize_bool_token(value)}
        escaped_name = html.escape(self.name)
        container_parts = []
        def add_part(part):
            if part and part not in container_parts:
                container_parts.append(part)

        add_part("form-check")
        outer_tokens = self.outer_class.split() if self.outer_class else []
        if self.inline:
            add_part("form-check-inline")
            # Drop grid width tokens when inline to keep radios truly inline
            outer_tokens = [t for t in outer_tokens if not t.startswith("col-")]
        for token in outer_tokens:
            add_part(token)
        container_class = " ".join(container_parts).strip()

        checkboxes_html = "".join(
            f'''
            <div class="{html.escape(container_class)}">
                <input class="form-check-input {html.escape(self.class_name)}" type="radio" 
                       name="{escaped_name}" id="{escaped_name}_{i}" value="{html.escape(str(val))}" 
                       {"checked" if val in value_set else ""} {"disabled" if str(val) in self.disabled_options else ""} {self.explode_data_attributes()}{disabled_attr}>
                <label class="form-check-label" for="{escaped_name}_{i}">{html.escape(str(lbl))}</label>
                {self._render_description(val)}
            </div>
            '''
            for i, (val, lbl) in enumerate(self._generate_option_html(self.options))
        )

        return f'{self.render_label()}{checkboxes_html}'

    def _generate_option_html(self, options):
        for option in options:
            if isinstance(option, str):
                norm_val = self._normalize_bool_token(option)
                yield norm_val, option
            elif isinstance(option, tuple):
                val, lbl = option
                yield self._normalize_bool_token(val), lbl
            elif isinstance(option, dict):
                for key, label in option.items():
                    yield self._normalize_bool_token(key), label

    def _render_description(self, option_value) -> str:
        desc = self.option_descriptions.get(str(option_value))
        if not desc:
            return ""
        return f'<div class="form-text">{html.escape(str(desc))}</div>'

