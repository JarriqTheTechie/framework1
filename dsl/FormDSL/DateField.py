from framework1.dsl.FormDSL.BaseField import BaseField
from framework1.dsl.FormDSL.TextField import TextField


class DateField(TextField):
    def __init__(self, name: str):
        super().__init__(name)
        self.set_field_type("date")
        self.set_data_attribute("data-type", "date")

    def set_link_to_lower_limit_field(self, field_name: str) -> 'DateField':
        self.set_data_attribute("data-date-for-lower-limit", field_name)
        return self

    def set_link_to_upper_limit_field(self, field_name: str) -> 'DateField':
        self.set_data_attribute("data-date-for-upper-limit", field_name)
        return self


class DateTimeField(TextField):
    def __init__(self, name: str):
        super().__init__(name)
        self.set_field_type("datetime-local")
        self.set_data_attribute("data-type", "datetime")

    def set_link_to_lower_limit_field(self, field_name: str) -> 'DateTimeField':
        self.set_data_attribute("data-datetime-for-lower-limit", field_name)
        return self

    def set_link_to_upper_limit_field(self, field_name: str) -> 'DateTimeField':
        self.set_data_attribute("data-datetime-for-upper-limit", field_name)
        return self


