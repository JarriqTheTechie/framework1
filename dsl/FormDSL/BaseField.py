import inspect
import pprint
from typing import List, Callable, Optional, Any

from framework1.dsl.FormDSL.Validation import ValidationRule


class BaseField:
    def __init__(self, name: str, field_type: str):
        self.visible = True
        self.name = name
        self.header = name  # Default to the name if no header is set
        self.class_name = ""
        self.label_class = ""
        self.field_type = field_type
        self.style = ""
        self.data_attributes = {}
        self.readonly = False
        self.disabled = False
        self.hidden = ""
        self.field_hidden = ""
        self.value_if_missing = ""
        self.script = ""
        self.help_text = ""  # New attribute for help text
        self.validation_rules: List[ValidationRule] = []
        self.__value_if_missing = ""
        self.__modify_using_ = None
        self.form = None
        self.outer_class = ""
        self.label_position = "above"  # Default position for label
        self.help_text_position = "below"

    def set_name(self, name: str):
        """Set the name of the field."""
        self.name = name
        return self

    def set_outer_class(self, outer_class: str) -> 'BaseField':
        """Set an outer class for the field, useful for styling."""
        self.outer_class = outer_class
        return self

    def get_outer_class(self) -> str:
        """Get the outer class for the field."""
        return self.outer_class

    def js_inline(self, multiline_js: str) -> str:
        """
        Converts multiline JavaScript into a safe single-line version.
        Trims whitespace and collapses to one space between tokens.
        """
        return " ".join(line.strip() for line in multiline_js.strip().splitlines())

    def set_label(self, header: str | Callable) -> 'BaseField':
        if callable(header):
            # If header is a callable, we assume it will be called later with the record
            self.header = header
        if isinstance(header, str):
            self.header = header
        return self

    def set_label_class(self, class_name: str) -> 'BaseField':
        self.label_class = class_name
        return self

    def set_style(self, style: str) -> 'BaseField':
        """Sets inline CSS style for the field."""
        self.style = style
        return self

    def set_class(self, class_name: str) -> 'BaseField':
        self.class_name = class_name
        return self

    def set_data_attribute(self, key: str, value: str, js_inline=False) -> 'BaseField':
        """Set a data attribute for the field."""
        if not js_inline:
            self.data_attributes[key] = value
        else:
            self.data_attributes[key] = self.js_inline(value).rstrip(";").strip()
            print(self.js_inline(value).rstrip(";").strip())
        return self

    def explode_data_attributes(self) -> str:
        """Return all data attributes in HTML format."""
        return " ".join([f'{key}="{value}"' for key, value in self.data_attributes.items()])

    def set_help_text(self, help_text: str | Callable) -> 'BaseField':
        """Set help text for the field, displayed below the label."""
        if callable(help_text) or isinstance(help_text, str):
            self.help_text = help_text
        return self

    def set_readonly(self, readonly: bool = True) -> 'BaseField':
        self.readonly = readonly
        return self

    def set_disabled(self, disabled: bool = True) -> 'BaseField':
        self.disabled = disabled
        return self

    def set_hidden(self, lambda_func: Callable | bool=True) -> 'BaseField':
        """Set a lambda function to determine if the field should be hidden."""
        match lambda_func:
            case True:
                self.hidden = "hidden"
                self.field_hidden = "d-none "
            case False:
                self.hidden = ""
            case _:
                self.hidden = "hidden"
                self.field_hidden = "d-none "
            
        return self

    def set_script(self, script: str) -> 'BaseField':
        """Set a script to be run when the field is interacted with."""
        self.script = script
        return self

    def default(self, value_if_missing: str) -> 'BaseField':
        self.__value_if_missing = value_if_missing
        return self

    def add_validation(self, validation_func: Callable, error_message: str) -> 'BaseField':
        """Add a custom validation rule to the field."""
        self.validation_rules.append(ValidationRule(validation_func, error_message))
        return self

    def is_required(self, error_message="This field is required.") -> 'BaseField':
        """Add a 'required' validation rule."""
        return self.add_validation(lambda v: v is not None and v != "", error_message)

    def min_length(self, length: int, error_message=None) -> 'BaseField':
        """Add a 'min_length' validation rule."""
        error_message = error_message or f"Must be at least {length} characters long."
        return self.add_validation(lambda v: v is not None and len(v) >= length, error_message)

    def max_length(self, length: int, error_message=None) -> 'BaseField':
        """Add a 'max_length' validation rule."""
        error_message = error_message or f"Must be at most {length} characters long."
        return self.add_validation(lambda v: v is not None and len(v) <= length, error_message)

    def pattern(self, regex: str, error_message="Invalid format.") -> 'BaseField':
        """Add a 'pattern' validation rule using a regex."""
        import re
        return self.add_validation(lambda v: re.match(regex, v) is not None, error_message)

    def validate(self, value) -> List[str]:
        """Run all validations and return a list of error messages (if any)."""
        errors = []
        for rule in self.validation_rules:
            error = rule.validate(value)
            if error:
                errors.append(error)
        return errors

    def render_label(self, record=None, data=None) -> str:
        if callable(self.header):
            header_text = self.header(record, data)
        else:
            header_text = self.header
        return f"""
        <label class="{self.label_class} {self.field_hidden}" for="{self.name}">
            {header_text}
        </label> 
        """

    def render_help_text(self, record=None, data=None) -> str:
        if callable(self.help_text):
            # If help_text is a callable, we assume it will be called later with the record and data
            help_text_html = f'<small class="help-text">{self.help_text(record, data)}</small>'
        elif isinstance(self.help_text, str):
            # If help_text is a string, we render it directly
            help_text_html = f'<small class="help-text">{self.help_text}</small>'
        return help_text_html

    def set_help_text_position(self, position: str) -> 'BaseField':
        match position.lower():
            case "above":
                self.help_text_position = "above"
            case "below":
                self.help_text_position = "below"
            case "top":
                self.help_text_position = "above"
            case "bottom":
                self.help_text_position = "below"
            case _:
                raise Exception(f"Invalid position: {position} for help text on field {self.name}. Use 'above' or 'below'.")
        self.help_text_position = position
        return self

    def modify_using(self, modify_using_: callable):
        self.__modify_using_ = modify_using_
        return self

    def visible_on(self, boolean: bool) -> 'BaseField':
        """Set the visibility of the field."""
        self.visible = boolean
        return self

    def _format_value(self, value, record):
        if value is None or value == "":
            value = self.__value_if_missing

        if self.__modify_using_:
            sig = inspect.signature(self.__modify_using_)
            try:
                if len(sig.parameters) == 2:
                    return self.__modify_using_(value, record)
                else:
                    return self.__modify_using_(value)
            except Exception:
                return value
        return value

    def set_label_position(self, position: str) -> 'BaseField':
        match position.lower():
            case "above":
                self.label_position = "above"
            case "below":
                self.label_position = "below"
            case "top":
                self.label_position = "above"
            case "bottom":
                self.label_position = "below"
            case _:
                raise Exception(f"Invalid position: {position} for label on field {self.name}. Use 'above' or 'below'.")
        self.label_position = position
        return self

    def render_input(self, value="", record={}) -> str:
        readonly_attr = " readonly" if self.readonly else ""
        disabled_attr = " disabled" if self.disabled else ""
        modified_value = self._format_value(value, record)
        # raise Exception(self.render_label(record, modified_value))
        if self.visible:
            return f"""
            {self.render_label(record, modified_value) if self.label_position == "above" else ""}
            {self.render_help_text(record, modified_value) if self.help_text and self.help_text_position == "above" else ""}
            <input type="{self.field_type}" 
                   id="{self.name}" 
                   name="{self.name}" 
                   {self.explode_data_attributes()} 
                   value="{modified_value}" 
                   class="{self.class_name}" 
                   style="{self.style}"
                   {readonly_attr}{disabled_attr} {self.hidden}/>
            {self.render_label(record, modified_value) if self.label_position == "below" else ""}
            {self.render_help_text(record, modified_value) if self.help_text and self.help_text_position == "below" else ""}
            {self.script}
            """

        return ""

class RawField(BaseField):
    def __init__(self, name: str, field_type: str = "text"):
        super().__init__(name, field_type)
        self.field_type = "raw"  # Override to indicate this is a raw field

    def render_input(self, value="", record={}) -> str:
        modified_value = self._format_value(value, record)
        if self.visible:
            return (f'{modified_value}')
        return ""