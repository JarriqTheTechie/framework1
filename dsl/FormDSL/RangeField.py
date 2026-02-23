from framework1.dsl.FormDSL.NumberField import NumberField


class RangeField(NumberField):
    """HTML5 range/slider input with min/max/step support."""

    def __init__(self, name: str):
        super().__init__(name)
        self.set_field_type("range")
        self.set_data_attribute("data-type", "range")
