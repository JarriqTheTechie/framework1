from typing import Callable, Self

from .fields import Field


class MasterDetailRow:
    def __init__(self, name: str):
        self.name = name
        self.data = ""
        self.raw_html = ""
        self.fields = []

    @staticmethod
    def make(name):
        return MasterDetailRow(name)

    def schema(self, fields: list[Field] = None) -> list[Field]:
        self.fields = fields if fields else []
        return self

    def set_data(self, data):
        self.data = data
        return self

    def template(self, template: str | Callable) -> Self:
        self._template = template
        return self
