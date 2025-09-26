from framework1.dsl.FormDSL.BaseField import BaseField


class TextField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "text")

    def set_field_type(self, field_type: str) -> 'TextField':
        self.field_type = field_type
        return self
