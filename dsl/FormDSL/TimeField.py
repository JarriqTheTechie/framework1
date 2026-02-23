from framework1.dsl.FormDSL.TextField import TextField


class TimeField(TextField):
    """HTML5 time input."""

    def __init__(self, name: str):
        super().__init__(name)
        self.set_field_type("time")
        self.set_data_attribute("data-type", "time")
