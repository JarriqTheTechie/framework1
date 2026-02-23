from framework1.dsl.FormDSL.TextField import TextField


class ColorField(TextField):
    """HTML5 color picker input."""

    def __init__(self, name: str):
        super().__init__(name)
        self.set_field_type("color")
        self.set_data_attribute("data-type", "color")
