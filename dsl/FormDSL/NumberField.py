from framework1.dsl.FormDSL.TextField import TextField
from typing import Self

from framework1.dsl.FormDSL.BaseField import BaseField


class NumberField(TextField):
    def __init__(self, name: str):
        super().__init__(name)
        self.set_field_type("number")
        self.min = None
        self.max = None
        self.step = None
        self.set_data_attribute("data-type", "number")

    def set_link_to_lower_limit_field(self, link_to: str = "") -> Self:
        """
        Link this number field to another field by specifying the other field's name.
        This can be used for validation or dynamic updates based on the linked field's value.
        :param link_to: The name of the field to link to.
        :return: Self for method chaining.
        """
        self.set_data_attribute("data-number-for-lower-limit-number", link_to)
        return self
    
    def set_link_to_upper_limit_field(self, link_to: str = "") -> Self:
        """
        Link this number field to another field by specifying the other field's name.
        This can be used for validation or dynamic updates based on the linked field's value.
        :param link_to: The name of the field to link to.
        :return: Self for method chaining.
        """
        self.set_data_attribute("data-number-for-upper-limit-number", link_to)
        return self

    def set_min(self, min_value: int) -> Self:
        self.set_data_attribute("min", min_value)
        return self

    def set_max(self, max_value: int) -> Self:
        self.set_data_attribute("min", max_value)
        return self

    def set_step(self, step_value: int) -> Self:
        self.step = step_value
        return self
