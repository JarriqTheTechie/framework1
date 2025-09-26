from framework1.dsl.FormDSL.BaseField import BaseField


class PasswordField(BaseField):
    def __init__(self, name: str):
        super().__init__(name, "password")