from framework1.dsl.FormDSL.DateField import DateTimeField


class DateTimePickerField(DateTimeField):
    """
    Alias for a datetime-local picker; keeps linkage helpers from DateTimeField.
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.set_data_attribute("data-type", "datetime-picker")
