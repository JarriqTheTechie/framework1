from framework1.dsl.Table import Field
from typing import Callable
from markupsafe import Markup

class IconColumn:
    def __init__(self, name):
        self._name = name
        self._icon_class = name  # Default icon class
        self._color_class = ""
        self._tooltip = None
        self._class_name = ""
        self._inner_field = Field(name).label("")  # Use a blank label if desired
        self._icon_size = ""

        # Disable most formatting logic in the inner field
        self._inner_field.modify_using(self._format_value)

    def name(self):
        return self._name

    def header(self):
        return self._inner_field.header()

    def class_name(self):
        return self._class_name

    def classes(self, class_name: str):
        self._class_name = f"{self._class_name} {class_name}".strip()
        return self

    def label(self, label: str):
        self._inner_field.label(label)
        return self

    def icon(self, icon_class_or_icon_map: str | Callable | dict):
        if isinstance(icon_class_or_icon_map, dict):
            self._icon_class = lambda record: icon_class_or_icon_map.get(record.get(self._name), "")
        elif callable(icon_class_or_icon_map):
            self._icon_class = icon_class_or_icon_map
        else:
            self._icon_class = icon_class_or_icon_map
        return self

    def color(self, color_or_color_map: str | Callable | dict):
        if isinstance(color_or_color_map, dict):
            self._color_class = lambda record: color_or_color_map.get(record.get(self._name), "")
        elif callable(color_or_color_map):
            self._color_class = color_or_color_map
        else:
            self._color_class = f"text-{color_or_color_map}"
        return self

    def size(self, size: str):
        self._icon_size = f"{size}" if size else ""
        return self

    def tooltip(self, tooltip: str | Callable):
        self._tooltip = tooltip
        return self

    def field(self) -> Field:
        """Return the composed Field instance, ready for schema()."""
        return self._inner_field

    def _format_value(self, _, record):
        icon = self._icon_class(record) if callable(self._icon_class) else self._icon_class
        color = f"text-{self._color_class(record) if callable(self._color_class) else self._color_class}"
        size = self._icon_size if hasattr(self, '_icon_size') else ""
        tooltip = ""

        if self._tooltip:
            tip = self._tooltip(record) if callable(self._tooltip) else self._tooltip
            tooltip = f' title="{tip}" data-bs-toggle="tooltip"'

        return Markup(f'<i class="{icon} {color} {size}"{tooltip}></i>')











