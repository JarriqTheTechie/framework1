from framework1.dsl.FormDSL.TextField import TextField


class TelField(TextField):
    """HTML5 telephone input."""

    def __init__(self, name: str):
        super().__init__(name)
        self.set_field_type("tel")
        self.set_data_attribute("data-type", "tel")
