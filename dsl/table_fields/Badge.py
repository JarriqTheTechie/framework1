from framework1.dsl.Table import Field


class Badge(Field):
    def __init__(self, name):
        super().__init__(name)
        self.__map = dict()
        self.__badge_class = ""


    def map(self, map: list[dict]):
        self.__map = map
        return self


    def _format_value(self, value, record):
        for combination in self.__map:
            if combination.get(value):
                self.__badge_class = combination.get(value)

        return f"""
            <span class="badge {self.class_name()} {self.__badge_class}">{value}</span>
        """
