from framework1.dsl.FormDSL.SelectField import SelectField
from framework1.dsl.FormDSL.TextField import TextField
from markupsafe import Markup
import re


def fix_inline_js_quotes(js: str) -> str:
    """
    Fix broken inline JS caused by double quotes inside HTML attributes.
    Ensures inner JS strings use single quotes.
    """
    # Replace any double-quoted JS string with single quotes
    return re.sub(r'"([^"]*?)"', r"'\1'", js)


class MoneyField(TextField):
    def __init__(self, name: str):
        super().__init__(name)
        self.set_data_attribute("data-type", "currency")


class CurrencySelectField(SelectField):
    def __init__(self, name: str):
        super().__init__(name)

    def set_currency_for(self, link_to: str = ""):
        """
        Link this currency selector to a MoneyField by specifying the MoneyField's name.
        This will enable auto-updating of the currency symbol in the linked MoneyField when a currency is selected.
        :param name: The name of the MoneyField to link to.
        :param link_to:
        :return:
        """
        self.set_data_attribute("data-currency-for", link_to)
        return self
