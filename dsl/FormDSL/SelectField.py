from typing import Tuple, Union, List, Self, Dict, Any
import json
import html
import re
from typing import Callable
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
        self.placeholder: str | None = None
        self.allow_clear: bool = False
        self.multiple: bool = False
        self.disabled_options: set[str] = set()
        self.option_descriptions: Dict[str, str] = {}
        # enhanced behaviors
        self.searchable: bool = False
        self.search_min_chars: int = 0
        self.max_items: int | None = None
        self.remote_url: str | None = None
        self.remote_method: str = "GET"
        self.remote_params: Dict[str, Any] | None = None
        self.remote_lazy: bool = True
        self.remote_min_chars: int = 1
        # Optional key used by Form batch option loaders.
        self.options_key: str | None = None
        self.options_transform: Callable[[Any], Any] | None = None

    def set_options(
        self,
        options: Union[List[str], List[Tuple[str, str]], List[Dict[str, Any]]]
    ) -> Self:
        self.options = options
        return self

    def set_placeholder(self, placeholder: str, allow_clear: bool = True) -> Self:
        self.placeholder = placeholder
        self.allow_clear = allow_clear
        return self

    def set_multiple(self, multiple: bool = True) -> Self:
        self.multiple = multiple
        return self

    def set_options_key(self, key: str) -> Self:
        """
        Attach a batch-loader key for this select.
        When the parent Form has a select options loader configured, fields sharing
        the same key are resolved in one batched loader call.
        """
        self.options_key = key
        return self

    def set_options_transform(self, transform: Callable[[Any], Any]) -> Self:
        """
        Optional transform applied to each loaded option for this field only.
        Useful when multiple fields share a key but need small per-field shaping.
        """
        self.options_transform = transform
        return self

    def disable_options(self, values: List[Any]) -> Self:
        self.disabled_options = { _normalize_for_compare(v) for v in values }
        return self

    def descriptions(self, descriptions: Dict[Any, str]) -> Self:
        self.option_descriptions = { _normalize_for_compare(k): v for k, v in descriptions.items() }
        return self

    def set_searchable(self, searchable: bool = True, min_chars: int = 0) -> Self:
        self.searchable = searchable
        self.search_min_chars = min_chars
        return self

    def set_max_items(self, max_items: int) -> Self:
        self.max_items = max_items
        return self

    def set_remote(self, url: str, method: str = "GET", params: Dict[str, Any] | None = None,
                   lazy: bool = True, min_chars: int = 1) -> Self:
        """
        Configure remote/async option loading. Expects frontend JS to honor data attributes.
        """
        self.remote_url = url
        self.remote_method = method.upper()
        self.remote_params = params or {}
        self.remote_lazy = lazy
        self.remote_min_chars = min_chars
        return self

    def render_input(self, value: Any = "", record: Dict[str, Any] = {}) -> str:
        if not self.visible:
            return ""
        disabled_attr = " disabled" if self.disabled else ""
        effective_multiple = self.multiple or str(self.name).endswith("[]")
        multiple_attr = ' multiple="multiple"' if effective_multiple else ""
        name_attr = f'{self.name}[]' if effective_multiple and not str(self.name).endswith("[]") else self.name

        # Generate HTML for options and optgroups
        options_html = "".join(self._generate_option_html(self.options, value))

        # Placeholder (only for single selects)
        placeholder_html = ""
        if self.placeholder and not effective_multiple:
            placeholder_selected = "selected" if (value in ("", None) or _normalize_for_compare(value) == "") else ""
            disabled_flag = "" if self.allow_clear else "disabled"
            placeholder_html = f'<option value="" {placeholder_selected} {disabled_flag}>{html.escape(self.placeholder)}</option>'

        if callable(self.help_text):
            help_text = self.help_text(record, value)
        else:
            help_text = self.help_text if self.help_text else ""

        # data attributes for JS enhancers
        enhancer_attrs = []
        if self.searchable:
            enhancer_attrs.append(f'data-select-searchable="1"')
            enhancer_attrs.append(f'data-select-min-chars="{self.search_min_chars}"')
        if self.max_items is not None:
            enhancer_attrs.append(f'data-select-max-items="{self.max_items}"')
        if self.remote_url:
            enhancer_attrs.append(f'data-select-remote-url="{html.escape(self.remote_url)}"')
            enhancer_attrs.append(f'data-select-remote-method="{html.escape(self.remote_method)}"')
            if self.remote_params:
                enhancer_attrs.append(f"data-select-remote-params='{html.escape(json.dumps(self.remote_params))}'")
            enhancer_attrs.append(f'data-select-remote-lazy="{1 if self.remote_lazy else 0}"')
            enhancer_attrs.append(f'data-select-remote-min-chars="{self.remote_min_chars}"')
        enhancer_attrs_str = " ".join(enhancer_attrs)

        return f"""
        {self.render_label(value, record) if self.label_position == "above" else ""}
        <select name="{html.escape(name_attr)}" 
                class="{html.escape(self.class_name)}" 
                {self.explode_data_attributes()} {enhancer_attrs_str}
                {disabled_attr}{multiple_attr}>
            {placeholder_html}
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
                disabled = "disabled" if val_str in self.disabled_options else ""
                title_attr = self._option_title(val_str)
                yield f'<option value="{html.escape(val_str)}" {selected} {disabled}{title_attr}>{html.escape(str(option))}</option>'

            # Tuple (value, label)
            elif isinstance(option, tuple):
                val, lbl = option
                val_str = _normalize_for_compare(val)
                selected = "selected" if val_str == normalized_selected or val_str in selected_set else ""
                disabled = "disabled" if val_str in self.disabled_options else ""
                title_attr = self._option_title(val_str)
                yield f'<option value="{html.escape(val_str)}" {selected} {disabled}{title_attr}>{html.escape(str(lbl))}</option>'

            # Dict (could be group or simple map)
            elif isinstance(option, dict):
                if "group" in option and "options" in option:
                    group_html = f'<optgroup label="{html.escape(str(option["group"]))}">'
                    for sub in option["options"]:
                        val = sub.get("value")
                        lbl = sub.get("label", val)
                        val_str = _normalize_for_compare(val)
                        selected = "selected" if val_str == normalized_selected or val_str in selected_set else ""
                        disabled = "disabled" if val_str in self.disabled_options else ""
                        title_attr = self._option_title(val_str)
                        group_html += f'<option value="{html.escape(val_str)}" {selected} {disabled}{title_attr}>{html.escape(str(lbl))}</option>'
                    group_html += "</optgroup>"
                    yield group_html
                elif "value" in option and "label" in option:
                    val = option["value"]
                    lbl = option["label"]
                    val_str = _normalize_for_compare(val)
                    selected = "selected" if val_str == normalized_selected or val_str in selected_set else ""
                    disabled = "disabled" if val_str in self.disabled_options else ""
                    title_attr = self._option_title(val_str)
                    yield f'<option value="{html.escape(val_str)}" {selected} {disabled}{title_attr}>{html.escape(str(lbl))}</option>'
                else:
                    for val, lbl in option.items():
                        val_str = _normalize_for_compare(val)
                        selected = "selected" if val_str == normalized_selected or val_str in selected_set else ""
                        disabled = "disabled" if val_str in self.disabled_options else ""
                        title_attr = self._option_title(val_str)
                        yield f'<option value="{html.escape(val_str)}" {selected} {disabled}{title_attr}>{html.escape(str(lbl))}</option>'

    def _option_title(self, value_key: str) -> str:
        desc = self.option_descriptions.get(value_key)
        return f' title="{html.escape(str(desc))}"' if desc else ""

