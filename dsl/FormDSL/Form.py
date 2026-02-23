from framework1.utilities.DataKlass import DataKlass
from typing import Self, Union, Callable, List, Dict, Tuple, Optional, Any
import json

from flask import Response
from markupsafe import Markup
import html

from framework1.dsl.FormDSL.BaseField import BaseField
from framework1.dsl.FormDSL.FieldGroup import FieldGroup
from framework1 import profile_component


class Form:
    def __init__(self, data: dict | DataKlass):
        self.submit_button_style = ""
        self.visible = True
        self.enctype = ""
        self.csrf_token: str | None = None
        self.data = data
        self.field_type = ""
        self.errors: Dict[str, List[str]] = {}
        self.class_name = ""
        self.submit_button_text = "Submit"
        self.submit_button_class = ""
        self.method = "POST"
        self.action = ""
        self.style = ""
        self.data_attributes = {}
        self.show_error_banner = False
        self.error_banner_class = "alert alert-danger"
        self.error_banner_title = "Please fix the errors below."
        self.auto_focus_errors = False
        # Per-instance schema caches (safe for dynamic options/data on a single form instance).
        self._schema_items_cache: List[BaseField | FieldGroup] | None = None
        self._schema_flat_fields_cache: List[BaseField] | None = None
        # Optional batch select-option loader.
        self._select_options_loader: Optional[Callable[[List[str], "Form"], Dict[str, List[Any]]]] = None
        self._select_options_cache: Dict[str, List[Any]] = {}
        # Cached conditional dependency graph compiled from field rules.
        self._conditional_dependency_graph_cache: Dict[str, Any] | None = None

    def get_create_button_text(self) -> str:
        """Override this method to customize create button text."""
        return "Create"

    def get_update_button_text(self) -> str:
        """Override this method to customize update button text."""
        return "Update"

    def get_id_key(self) -> str:
        """Override this method to customize the key used for ID detection."""
        return "id"

    def detect_form_action(self, data: dict[str, Any], store_action: Callable, update_action: Callable) -> 'Form':
        """
        Simple helper to set appropriate form action based on data.

        Args:
            data: Form data dictionary
            store_action: Create/Store action method
            update_action: Edit/Update action method
        """
        id_key = self.get_id_key()
        if data and id_key in data and data[id_key]:
            self.set_submit_button_text(self.get_update_button_text())
            # self.set_form_action(update_action, **{id_key: data[id]})
            self.set_form_action(update_action, **{"id": data[id_key]})
        else:
            self.set_submit_button_text(self.get_create_button_text())
            self.set_form_action(store_action)
        return self

    def set_method(self, method: str) -> 'Form':
        self.method = method
        return self

    def set_class(self, class_name: str) -> 'Form':
        self.class_name = class_name
        return self

    def set_style(self, style: str) -> 'Form':
        """Sets inline CSS style for the form."""
        self.style = style
        return self

    def set_submit_button_text(self, text: str) -> 'Form':
        self.submit_button_text = text
        return self

    def set_submit_button_class(self, class_name: str) -> 'Form':
        self.submit_button_class = class_name
        return self

    def set_submit_button_style(self, style: str) -> 'Form':
        self.submit_button_style = style
        return self

    def set_form_action(self, action: str | Response | Callable, **kwargs) -> 'Form':
        if isinstance(action, (Response, Callable)):
            from flask import url_for
            self.action = url_for(action.__name__, **kwargs)
        else:
            self.action = str(action)
        return self

    def schema(self) -> List[BaseField | FieldGroup]:
        """Override this method to define schema."""
        return []

    def invalidate_schema_cache(self) -> "Form":
        self._schema_items_cache = None
        self._schema_flat_fields_cache = None
        self._conditional_dependency_graph_cache = None
        return self

    def set_select_options_loader(
        self,
        loader: Callable[[List[str], "Form"], Dict[str, List[Any]]]
    ) -> "Form":
        """
        Configure a batched select-options loader.
        Loader receives unique keys used by SelectField.set_options_key(...) and must return:
          { "key": [options...] }
        """
        self._select_options_loader = loader
        return self

    def invalidate_select_options_cache(self) -> "Form":
        self._select_options_cache = {}
        return self

    def _get_schema_items(self) -> List[BaseField | FieldGroup]:
        if self._schema_items_cache is None:
            items = self.schema()
            self._schema_items_cache = items if items is not None else []
        return self._schema_items_cache

    def _get_schema_flat_fields(self) -> List[BaseField]:
        if self._schema_flat_fields_cache is not None:
            return self._schema_flat_fields_cache

        fields: List[BaseField] = []
        for item in self._get_schema_items():
            if isinstance(item, FieldGroup):
                fields.extend(item.fields)
            else:
                fields.append(item)
        self._schema_flat_fields_cache = fields
        return fields

    def _safe_json_value(self, value: Any) -> Any:
        try:
            json.dumps(value)
            return value
        except Exception:
            return str(value)

    def _compile_conditional_dependency_graph(self) -> Dict[str, Any]:
        edges: Dict[str, List[str]] = {}
        fields: Dict[str, List[Dict[str, Any]]] = {}

        for field in self._get_schema_flat_fields():
            get_rules = getattr(field, "get_visibility_conditions", None)
            if not callable(get_rules):
                continue
            rules = get_rules() or []
            if not rules:
                continue

            target = str(getattr(field, "name", ""))
            compiled_rules: List[Dict[str, Any]] = []
            for rule in rules:
                sources = [str(s) for s in (rule.get("sources") or []) if s is not None and str(s) != ""]
                compiled = {
                    "sources": sources,
                    "operator": str(rule.get("operator", "equals")),
                    "value": self._safe_json_value(rule.get("value")),
                    "mode": str(rule.get("mode", "show")),
                }
                compiled_rules.append(compiled)
                for source in sources:
                    edges.setdefault(source, [])
                    if target not in edges[source]:
                        edges[source].append(target)

            if target and compiled_rules:
                fields[target] = compiled_rules

        return {
            "version": 1,
            "edges": edges,
            "fields": fields,
        }

    def _get_conditional_dependency_graph(self) -> Dict[str, Any]:
        if self._conditional_dependency_graph_cache is None:
            self._conditional_dependency_graph_cache = self._compile_conditional_dependency_graph()
        return self._conditional_dependency_graph_cache

    def _prime_select_options(self) -> None:
        if not callable(self._select_options_loader):
            return

        schema_fields = self._get_schema_flat_fields()
        keyed_fields: Dict[str, List[BaseField]] = {}
        for field in schema_fields:
            if getattr(field, "field_type", None) != "select":
                continue
            options_key = getattr(field, "options_key", None)
            if not options_key:
                continue
            keyed_fields.setdefault(str(options_key), []).append(field)

        if not keyed_fields:
            return

        missing_keys = [k for k in keyed_fields.keys() if k not in self._select_options_cache]
        if missing_keys:
            loaded = self._select_options_loader(missing_keys, self)
            if isinstance(loaded, dict):
                for key, options in loaded.items():
                    if isinstance(options, list):
                        self._select_options_cache[str(key)] = options

        for options_key, fields in keyed_fields.items():
            base_options = self._select_options_cache.get(options_key)
            if base_options is None:
                continue
            for field in fields:
                transform = getattr(field, "options_transform", None)
                if callable(transform):
                    field.set_options([transform(o) for o in base_options])
                else:
                    field.set_options(base_options)

    def validate(self) -> bool:
        self.errors.clear()
        valid = True
        self._prime_select_options()

        for field in self._get_schema_flat_fields():
            value = self.data.get(field.name, "")
            field_errors = field.validate(value, context=self)
            if field_errors:
                self.errors[field.name] = field_errors
                valid = False
        return valid

    def render_errors(self, field_name) -> str:

        if field_name in self.errors:
            error_html = "".join(f'<p class="validation-error">{html.escape(str(error))}</p>' for error in self.errors[field_name])
            return f'<div class="error-messages mx-2">{error_html}</div>'
        return ""

    def render_non_field_errors(self, field_names: set[str]) -> str:
        """
        Render errors that are not tied to a specific field (e.g., form-level validation).
        """
        non_field_errors = {k: v for k, v in self.errors.items() if k not in field_names}
        if not non_field_errors:
            return ""

        error_html = "".join(
            "".join(f'<p class="validation-error">{html.escape(str(msg))}</p>' for msg in messages)
            for messages in non_field_errors.values()
        )
        return f'<div class="error-messages mx-2">{error_html}</div>'

    def visible_on(self, boolean: bool) -> 'Form':
        """Set the visibility of the form."""
        self.visible = boolean
        return self

    def set_enctype(self, enctype: str) -> 'Form':
        self.enctype = enctype
        return self

    def set_data(self, data: dict) -> 'Form':
        self.data = data
        self.invalidate_schema_cache()
        self.invalidate_select_options_cache()
        return self

    def set_data_attribute(self, key: str, value: str, js_inline=False) -> 'BaseField':
        """Set a data attribute for the field."""
        if not js_inline:
            self.data_attributes[key] = value
        else:
            self.data_attributes[key] = self.js_inline(value).rstrip(";").strip()
            print(self.js_inline(value).rstrip(";").strip())
        return self

    def show_errors_banner(self, title: str | None = None, css_class: str | None = None) -> 'Form':
        """Enable a form-level error banner rendered above the fields when errors exist."""
        self.show_error_banner = True
        if title:
            self.error_banner_title = title
        if css_class:
            self.error_banner_class = css_class
        return self

    def focus_errors(self, enable: bool = True) -> 'Form':
        """Auto-focus the first invalid field and scroll into view after render."""
        self.auto_focus_errors = enable
        return self

    def set_csrf_token(self, token: str) -> 'Form':
        """Attach a CSRF token that will be rendered as a hidden field."""
        self.csrf_token = token
        return self

    def explode_data_attributes(self) -> str:
        """Return all data attributes in HTML format."""
        return " ".join(
            [f'{html.escape(str(key))}="{html.escape(str(value))}"' for key, value in self.data_attributes.items()]
        )

    def render(self) -> Markup | str:
        component_name = self.__class__.__name__
        if self.visible:
            with profile_component(f"{component_name}.render.prepare", kind="form"):
                self._prime_select_options()
                conditional_graph = self._get_conditional_dependency_graph()
                conditional_fields = conditional_graph.get("fields", {})
                conditional_attr = ""
                if conditional_fields:
                    graph_json = html.escape(json.dumps(conditional_graph, separators=(",", ":"), ensure_ascii=True))
                    conditional_attr = f' data-f1-conditional-graph="{graph_json}"'

                html_str = f'<form action="{html.escape(self.action)}" method="{html.escape(self.method)}" class="{html.escape(self.class_name)}" id="{self.__class__.__name__}" style="{html.escape(self.style)}" enctype="{html.escape(self.enctype)}" {self.explode_data_attributes()}{conditional_attr} >\n'
            loop_counter = 1
            loop_length = 1  # len(self.schema())

            if self.show_error_banner and self.errors:
                html_str += f'<div class="{html.escape(self.error_banner_class)}" role="alert">{html.escape(self.error_banner_title)}</div>'

            # Collect field names for non-field error rendering
            field_names = set()
            
            with profile_component(f"{component_name}.render.schema", kind="form"):
                schema_items = self._get_schema_items()
                schema_fields = self._get_schema_flat_fields()

            with profile_component(f"{component_name}.render.fields", kind="form"):
                for item in schema_items:
                    if isinstance(item, FieldGroup):
                        item.form = self
                        html_str += item.render(self.data, self)
                        if loop_counter == loop_length:
                            pass
                        for field in item.fields:
                            try:
                                field_names.add(field.name)
                            except Exception:
                                pass
                    else:
                        value = self.data.get(item.name, "")
                        field_names.add(item.name)
                        # Determine container class per field
                        base_outer = item.get_outer_class() if hasattr(item, "get_outer_class") else ""
                        if base_outer:
                            outer_class = base_outer
                        else:
                            outer_class = "form-check" if getattr(item, "field_type", "") == "checkbox" else "form-group"

                        html_str += f'  <div class="{html.escape(outer_class)}">{item.render_input(value, item)}{self.render_errors(item.name)}</div>\n'
                    loop_counter += 1
            with profile_component(f"{component_name}.render.finalize", kind="form"):
                if schema_fields:
                    field_names.update({f.name for f in schema_fields if hasattr(f, "name")})
                # Render any form-level/non-field errors after inputs
                html_str += self.render_non_field_errors(field_names)
                if self.csrf_token:
                    html_str += f'<input type="hidden" name="csrf_token" value="{html.escape(self.csrf_token)}"/>'
                html_str += f'<div style="width: 100%"><button class="{html.escape(self.submit_button_class)}" type="submit" id="{self.__class__.__name__}_btn" style="{html.escape(self.submit_button_style)}">{html.escape(self.submit_button_text) if self.submit_button_text else "Submit"}</button></div>'
                html_str += f'\n</form>'
                if self.auto_focus_errors and self.errors:
                    first_error_field = next(iter(self.errors.keys()))
                    html_str += f"""
                    <script>
                    (function() {{
                      const field = document.getElementById("{html.escape(first_error_field)}");
                      if (field && typeof field.focus === "function") {{
                        field.focus();
                        if (typeof field.scrollIntoView === "function") {{
                          field.scrollIntoView({{ behavior: "smooth", block: "center" }});
                        }}
                      }}
                    }})();
                    </script>
                    """
        else:
            html_str = ""
        return Markup(html_str)

    def __str__(self) -> str:
        return self.render()
