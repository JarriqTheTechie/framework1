from typing import Callable, Union


class Field:
    def __init__(self, name):
        """The only required argument is the name."""
        self.__name = name
        self.__header = name  # Default to the name if no header is set
        self.__class_name = ""
        self.__modify_using_ = None
        self.__value_if_missing = ""
        self._icon_color = ""
        self._icon = None
        self._icon_position = "left"  # Default icon position
        self._icon_map = []
        self._outer_class = ""
        self._badge = False
        self._badge_color_map = []
        self._static_badge_color = None
        self._date_format = None
        self._render_html = False
        self._description = None
        self._description_position = "below"  # or "above"
        self._limit = None
        self._limit_end = "..."
        self._words_limit = None
        self._words_end = "..."
        self._sortable = False
        self._searchable = False
        self._tooltip = None
        self._extra_attributes = None
        self._extra_cell_attributes = None
        self._hidden = False

    def name(self):
        return self.__name

    def header(self):
        return self.__header

    def class_name(self):
        return self.__class_name

    def label(self, header: str):
        self.__header = header
        return self

    def placeholder(self, placeholder: str):
        self.__value_if_missing = placeholder
        return self

    def classes(self, class_name: str):
        self.__class_name = f"{self.__class_name} {class_name}" if self.__class_name else class_name
        return self

    def color(self, color: str):
        """Set the color class for the field."""
        if color:
            self.__class_name = f"{self.__class_name} text-{color}" if self.__class_name else f"text-{color}"
        return self

    def icon(self, icon: str | dict[str, str]):
        if isinstance(icon, str):
            self._icon = icon
        else:
            if isinstance(icon, dict):
                self._icon_map = icon
            else:
                raise TypeError("Icon must be a string or a dictionary mapping values to icons")
        return self

    def icon_position(self, position: str):
        """Set the position of the icon."""
        if position in ["left", "right"]:
            self._icon_position = position
        else:
            raise ValueError("Icon position must be 'left' or 'right'")
        return self

    def icon_color(self, color: str):
        """Set the color of the icon."""
        if color:
            self._icon_color = f"text-{color}"
        return self

    def badge(self):
        """Add a badge to the field."""
        self._badge = True
        return self

    def badge_color(self, color: str | dict[str, str]):
        """
        Set badge color either statically or using a value mapping.

        Args:
            color: Either a string for static color or dict mapping values to colors
        """
        if isinstance(color, str):
            self._static_badge_color = color
        else:
            self._badge_color_map = color
        return self

    def modify_using(self, modify_using_: callable):
        self.__modify_using_ = modify_using_
        return self

    def default(self, value_if_missing: str):
        self.__value_if_missing = value_if_missing
        return self

    def _format_value(self, value, record):
        """Apply modifier if exists, otherwise return the value."""
        if value is None or value == "":
            value = self.__value_if_missing
        if self.__modify_using_:
            try:
                return self.__modify_using_(value, record)
            except Exception as e:
                raise e
        return value

    def date(self, format_string: str = "%Y-%m-%d %H:%M:%S"):
        def date_formatter(value, _):
            if not value:
                return ""

            python_format = format_string

            try:
                from datetime import datetime
                if isinstance(value, str):
                    # Try parsing the string as datetime
                    try:
                        # Try ISO format first
                        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except ValueError:
                        # Try common formats
                        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                            try:
                                dt = datetime.strptime(value, fmt)
                                break
                            except ValueError:
                                continue
                        else:
                            return value  # Return original if parsing fails
                elif isinstance(value, (int, float)):
                    # Assume timestamp
                    dt = datetime.fromtimestamp(value)
                else:
                    # Assume it's already a datetime object
                    dt = value

                return dt.strftime(python_format)
            except Exception:
                return value  # Return original value if formatting fails

        self.modify_using(date_formatter)
        return self

    def html(self):
        """
        Allow the field value to be rendered as HTML.

        Returns:
            Self: Returns the field instance for method chaining
        """
        self._render_html = True
        return self

    def description(
        self,
        description_value: str | Callable,
        position: str = "below",
        limit: int = 100,
        end: str = "...",
        html: bool = False,
    ):
        """
        Add a description to the field content.

        Args:
            description_value: String or callable that takes the record and returns a string
            position: Position of description - "below" or "above" (default: "below")
        """
        if position not in ["below", "above"]:
            raise ValueError("Position must be either 'below' or 'above'")

        self._description = description_value
        self._description_position = position
        self._description_limit = limit
        self._description_limit_end = end
        self._description_is_html = html
        return self

    def limit(self, count: int | Callable, end: str = "..."):
        """
        Limit the length of the column's value.

        Args:
            count: Integer or callable that returns the maximum length
            end: String to append when text is truncated (default: "...")
        """
        self._limit = count
        self._limit_end = end
        return self

    def words(self, count: Union[int, Callable], end: str = "..."):
        """
        Limit the number of words in the column's value.
        """
        self._words_limit = count
        self._words_end = end
        return self

    def sortable(self):
        self._sortable = True
        return self

    def searchable(self):
        self._searchable = True
        return self

    def url(self, url_pattern):
        """
        Set a URL pattern or function for the field.
        Args:
            url_pattern (str | callable): URL template with placeholders (e.g., "/users/{id}")
                                          or a callable (record -> url)
        """
        self._url_template = url_pattern
        return self

    def tooltip(self, text_or_callable):
        """
        Set a tooltip for this field. Can be:
        - A static string
        - A callable that takes (record) or (record, data) and returns a string
        """
        self._tooltip = text_or_callable
        return self

    def extra_attributes(self, attrs):
        """
        Set additional HTML attributes for the <td> tag.
        Example: {"class": "slug-column", "data-slug": "value"}
        """
        self._extra_attributes = attrs
        return self

    def extra_cell_attributes(self, attrs):
        """
        Set additional attributes for the <td> tag (cell-specific).
        Supports static dict or callable(record).
        """
        self._extra_cell_attributes = attrs
        return self

    def hidden(self, value: bool | Callable = True):
        """
        Mark the field as hidden.
        Args:
            value (bool | Callable): True/False or a callable(record) -> bool
        """
        self._hidden = value
        return self


class TextColumn(Field):
    @staticmethod
    def make(name):
        return TextColumn(name)
