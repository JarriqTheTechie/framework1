from framework1.dsl.FormDSL.TextField import TextField


class UrlField(TextField):
    """HTML5 URL input."""

    def __init__(self, name: str):
        super().__init__(name)
        self.set_field_type("url")
        self.set_data_attribute("data-type", "url")
