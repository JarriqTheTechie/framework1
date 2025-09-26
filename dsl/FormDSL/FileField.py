from framework1.dsl.FormDSL.BaseField import BaseField


class FileField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "file")

    def set_field_type(self, field_type: str) -> 'FileField':
        self.field_type = field_type
        return self
