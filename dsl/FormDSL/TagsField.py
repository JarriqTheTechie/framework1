import html
import json
from typing import List, Union

from framework1.dsl.FormDSL.BaseField import BaseField


class TagsField(BaseField):
    """
    Simple tags/chips input that stores values as a comma-delimited string in the text box
    while also emitting a hidden JSON array for structured handling.
    """

    def __init__(self, name: str):
        super().__init__(name, "text")
        self.set_data_attribute("data-type", "tags")
        self.delimiter = ","
        self.placeholder = ""
        self.max_tags: int | None = None

    def set_placeholder(self, placeholder: str) -> "TagsField":
        self.placeholder = placeholder
        return self

    def set_delimiter(self, delimiter: str) -> "TagsField":
        self.delimiter = delimiter
        return self

    def set_max_tags(self, max_tags: int) -> "TagsField":
        self.max_tags = max_tags
        return self

    def render_input(self, value="", record={}) -> str:
        readonly_attr = " readonly" if self.readonly else ""
        disabled_attr = " disabled" if self.disabled else ""
        required_attr = " required" if self._required_attr else ""

        # normalize value to list then to delimited string
        tags_list: List[str]
        if isinstance(value, str):
            tags_list = [t.strip() for t in value.split(self.delimiter) if t.strip()]
        elif isinstance(value, list):
            tags_list = [str(t).strip() for t in value if str(t).strip()]
        else:
            tags_list = []

        display_value = self.delimiter.join(tags_list)
        json_value = json.dumps(tags_list)

        placeholder_attr = f' placeholder="{html.escape(self.placeholder)}"' if self.placeholder else ""
        max_tags_attr = f' data-max-tags="{self.max_tags}"' if self.max_tags is not None else ""

        escaped_name = html.escape(self.name)
        escaped_class = html.escape(self.class_name)
        escaped_style = html.escape(self.style)
        hidden_attr = html.escape(self.hidden)

        # Inline JS helper (framework-agnostic)
        helper_script = f"""
        <script>
        (function() {{
          const input = document.getElementById("{escaped_name}");
          const hidden = document.querySelector('input[name="{escaped_name}_json"]');
          if (!input || !hidden) return;
          const delimiter = "{html.escape(self.delimiter)}";
          const maxTags = {self.max_tags if self.max_tags is not None else 'null'};

          function normalize(val) {{
            return (val || "")
              .split(delimiter)
              .map(t => t.trim())
              .filter(Boolean);
          }}

          function render() {{
            const tags = normalize(input.value);
            if (maxTags !== null && tags.length > maxTags) {{
              tags.length = maxTags;
              input.value = tags.join(delimiter);
            }}
            hidden.value = JSON.stringify(tags);
          }}

          input.addEventListener("change", render);
          input.addEventListener("blur", render);
          render();
        }})();
        </script>
        """

        return f"""
        {self.render_label(record, value) if self.label_position == "above" else ""}
        <input type="text"
               id="{escaped_name}"
               name="{escaped_name}"
               value="{html.escape(display_value)}"
               {self.explode_data_attributes()}{placeholder_attr}{max_tags_attr}
               class="{escaped_class}"
               style="{escaped_style}"
               {readonly_attr}{disabled_attr}{required_attr} {hidden_attr}/>
        <input type="hidden"
               name="{escaped_name}_json"
               value="{html.escape(json_value)}"/>
        {helper_script}
        {self.render_label(record, value) if self.label_position == "below" else ""}
        {self.render_help_text(record, value) if self.help_text and self.help_text_position == "below" else ""}
        """
