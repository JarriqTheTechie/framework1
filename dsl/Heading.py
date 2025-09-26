from typing import Self

from markupsafe import Markup


class Heading:
    def __init__(self, level: int):
        self.level = level
        self.heading_text = ""
        self.heading_classes = ""
        self.extra_attrs = {}

    def label(self, text):
        self.heading_text = text
        return self

    def classes(self, class_name):
        self.heading_classes = class_name
        return self

    def extra_attributes(self, attrs: dict):
        self.extra_attrs = attrs
        return self

    def render(self):
        # Build the extra attributes
        extra_attrs_str = " ".join(f'{key}="{value}"' for key, value in self.extra_attrs.items())
        return Markup(f'<div class="h{self.level} {self.heading_classes}" {extra_attrs_str}>{self.heading_text}</div>')

    def __str__(self) -> Markup | Self:
        return self.render()


class Subheading(Heading):
    def __init__(self, level: int = 6):
        super().__init__(level)
        self.heading_classes = "text-muted"
        self.extra_attrs = {}