import pprint
from decimal import Decimal, InvalidOperation
from framework1.database.ActiveRecord import ActiveRecord
from framework1.database.active_record.utils.ModelCollection import ModelCollection
from framework1.database.QueryBuilder import QueryBuilder
from typing import Union

from framework1.utilities.DataKlass import DataKlass
from markupsafe import Markup
from typing_extensions import Callable


class InfoListField:
    def __init__(self, name, hide_if_empty: bool = False, default_value: str = ""):
        """The only required argument is the name."""
        self.__name = name
        self.__header = name  # Default to the name if no header is set
        self.__class_name = ""
        self.__label_class_name = ""
        self.__modify_using_ = None
        self.__value_if_missing = ""
        self._icon_color = ""
        self._icon = None
        self._icon_position = "left"  # Default icon position
        self._outer_class = ""
        self._badge = False
        self._badge_color_map = []
        self._static_badge_color = None
        self._date_format = None
        self._render_html = False
        self._description = None
        self._description_position = 'below'  # or 'above'
        self._limit = None
        self._limit_end = '...'
        self._words_limit = None
        self._words_end = '...'
        self._sortable = False
        self._searchable = False
        self._tooltip = None
        self._extra_attributes = None
        self._extra_cell_attributes = None
        self._hidden = False
        if hide_if_empty:
            self.hide_if_empty(default_value)

    def name(self):
        return self.__name

    def header(self):
        return self.__header

    def class_name(self):
        return self.__class_name

    def label(self, header: str | Callable):
        self.__header = header
        return self

    def placeholder(self, placeholder: str):
        self.__value_if_missing = placeholder
        return self

    def classes(self, class_name: str):
        self.__class_name = f"{self.__class_name} {class_name}" if self.__class_name else class_name
        return self

    def label_classes(self, class_name: str):
        """Set the CSS classes for the label."""
        if class_name:
            self.__label_class_name = f"{self.__label_class_name} {class_name}" if self.__label_class_name else class_name
        return self

    def get_label_classes(self):
        """Get the CSS classes for the label."""
        return self.__label_class_name

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
        from inspect import signature
        sig = signature(modify_using_)
        if len(sig.parameters) == 1:
            self.__modify_using_ = lambda value, record=None: modify_using_(value)
        else:
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
            except TypeError as e:
                print(str(e))
                return self.__modify_using_(value)
        return value

    def date(self, format_string: str = 'M j, Y'):
        """
        Format the field value as a date.

        Args:
            format_string: PHP-style date format string
                M = Month as 3-letter abbreviation
                j = Day of month without leading zeros
                Y = Full year
                Other formats:
                - y = 2-digit year
                - d = Day with leading zeros
                - F = Full month name
                - H = 24-hour format
                - h = 12-hour format
                - i = Minutes with leading zeros
                - s = Seconds with leading zeros
                - a = am/pm
                - A = AM/PM
        """

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
                        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except ValueError:
                        # Try common formats
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
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

    def description(self, description_value: str | Callable, position: str = 'below', limit: int = 100,
                    end: str = '...', html=False):
        """
        Add a description to the field content.

        Args:
            description_value: String or callable that takes the record and returns a string
            position: Position of description - 'below' or 'above' (default: 'below')
        """
        if position not in ['below', 'above']:
            raise ValueError("Position must be either 'below' or 'above'")

        self._description = description_value
        self._description_position = position
        self._description_limit = limit
        self._description_limit_end = end
        self._description_is_html = html
        return self

    def limit(self, count: int | Callable, end: str = '...'):
        """
        Limit the length of the column's value.

        Args:
            count: Integer or callable that returns the maximum length
            end: String to append when text is truncated (default: '...')
        """
        self._limit = count
        self._limit_end = end
        return self

    def words(self, count: Union[int, Callable], end: str = '...'):
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
        Example: {'class': 'slug-column', 'data-slug': 'value'}
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

    def is_hidden(self):
        return self._hidden

    def hide_if_empty(self, default_value: str = ""):
        """
        Hides the field if its value is None or an empty string.
        """
        return self.hidden(lambda value, data: value is None or value == "")

    def __format_currency(self, value: Decimal) -> str:
        try:
            value = Decimal(value)
            return "${:,.2f}".format(value)
        except (InvalidOperation, ValueError, TypeError):
            return str(value) if value is not None else "$0.00"

    def currency(self):
        return self.modify_using(
            lambda value, record: self.__format_currency(value)
        )

    def link(self, prefix: str = "", suffix: str = ""):
        """
        Wrap the field value in an anchor tag with optional prefix and suffix.
        """

        return self.modify_using(
            lambda value, record: Markup(f"<a href='{prefix}{value}{suffix}'>{value}</a>")
        )

    @classmethod
    def separator(cls):
        field = cls(name="__separator__")
        field._is_separator = True
        return field


class InfoList:
    def __init__(self, data: list[dict] | list[DataKlass] | list[ActiveRecord] | QueryBuilder = None, non_activerecord_model=None):
        self.pagination = None
        self.data = data
        self.query = None
        self._heading = None
        self._icon = None
        self._footer = None
        self._container_class = "card my-3 "
        self._heading_class = ""
        self._footer_class = ""
        self._infolist_body_class_from_field = "col-8"
        self._infolist_label_class_from_field = "col-4"

        # New grid config
        self._grid_mode = False
        self._grid_columns = 3  # default 3 per row

    def set_style(self, style: str):
        self._style = style
        return self

    def container_classeses(self, classes: str, include_default: bool = True):
        if include_default:
            self._container_class = self._container_class + classes
        else:
            self._container_class = classes
        return self

    def schema(self):
        return []

    # --- Grid config ---
    def as_grid(self, columns: int = 3):
        """Enable grid mode with N columns per row."""
        self._grid_mode = True
        self._grid_columns = max(1, columns)
        return self

    def as_list(self):
        """Disable grid mode (default)."""
        self._grid_mode = False
        return self

    # --- Existing heading/footer config ---
    def set_heading(self, heading: str | Callable):
        self._heading = heading
        return self

    def set_heading_class(self, class_name: str):
        self._heading_class = class_name
        return self

    def set_icon(self, icon: str | Callable):
        self._icon = icon
        return self

    def set_footer(self, footer: str | Callable):
        self._footer = footer
        return self

    def set_footer_class(self, class_name: str):
        self._footer_class = class_name
        return self

    # --- Content builder ---
    def build_cell_content(self, field: InfoListField, value: str, record) -> str:
        raw_value = value
        formatted_value = field._format_value(raw_value, record)

        # Character limit
        if hasattr(field, '_limit') and field._limit is not None:
            limit_value = field._limit(record) if callable(field._limit) else field._limit
            if isinstance(limit_value, int) and len(str(formatted_value)) > limit_value:
                formatted_value = str(formatted_value)[:limit_value] + field._limit_end

        # Word limit
        if hasattr(field, '_words_limit') and field._words_limit is not None:
            words_limit = field._words_limit(record) if callable(field._words_limit) else field._words_limit
            if isinstance(words_limit, int):
                words = str(formatted_value).split()
                if len(words) > words_limit:
                    formatted_value = ' '.join(words[:words_limit]) + field._words_end

        # HTML escaping
        if not getattr(field, '_render_html', False):
            from markupsafe import escape
            formatted_value = escape(formatted_value)

        content_parts = []

        # Icons
        icon_classes = []
        if getattr(field, '_icon_map', None) and formatted_value in field._icon_map:
            icon_classes.append(field._icon_map[formatted_value])
        if getattr(field, '_icon', None):
            icon_classes.append(self._icon)
        if getattr(field, '_icon_color', None):
            icon_classes.append(field._icon_color)

        icon_html = f'<i class="{" ".join(icon_classes)}"></i>' if icon_classes else ''
        if getattr(field, '_icon_position', 'left') == 'left':
            content_parts.append(f'{icon_html} ')
        else:
            content_parts.append(f' {icon_html}')

        # Main content
        content_parts.insert(
            1 if getattr(field, '_icon_position', 'left') == 'left' else 0,
            formatted_value
        )
        content = ''.join(content_parts)

        # Description
        if getattr(field, '_description', None):
            if callable(field._description):
                from inspect import signature
                sig = signature(field._description)
                if len(sig.parameters) == 2:
                    description_text = field._description(record, record)
                else:
                    description_text = field._description(record)
            else:
                description_text = field._description
            if description_text:
                from markupsafe import escape, Markup
                if not field._description_is_html:
                    content += f'<div class="text-muted small">{escape(str(description_text)[:field._description_limit])}{field._description_limit_end}</div>'
                else:
                    content += f'<div class="text-muted small">{Markup(description_text[:field._description_limit])}{field._description_limit_end}</div>'

        # Badges
        if getattr(field, '_badge', False):
            badge_classes = ['badge']
            color_key = None
            if getattr(field, '_badge_color_map', None):
                if raw_value in field._badge_color_map:
                    color_key = raw_value
                elif formatted_value in field._badge_color_map:
                    color_key = formatted_value
                if color_key:
                    badge_classes.append(f'bg-{field._badge_color_map[color_key]}')
            elif getattr(field, '_static_badge_color', None):
                badge_classes.append(f'bg-{field._static_badge_color}')
            content = f'<span class="{" ".join(badge_classes)}">{content}</span>'

        # URL wrapping
        if getattr(field, '_url_template', None):
            if callable(field._url_template):
                url = field._url_template(record)
            else:
                try:
                    url = field._url_template.format(**record.to_dict())
                except KeyError:
                    url = "#"
            content = f'<a href="{url}">{content}</a>'

        # Tooltip
        tooltip_html_open = tooltip_html_close = ""
        tooltip_text = None
        if getattr(field, '_tooltip', None):
            tooltip = field._tooltip
            if callable(tooltip):
                from inspect import signature
                sig = signature(tooltip)
                if len(sig.parameters) == 2:
                    tooltip_text = tooltip(record, record.to_dict())
                else:
                    tooltip_text = tooltip(record)
            else:
                tooltip_text = tooltip
        if tooltip_text:
            from markupsafe import escape
            tooltip_html_open = f'<span data-bs-toggle="tooltip" title="{escape(tooltip_text)}">'
            tooltip_html_close = '</span>'

        return f'{tooltip_html_open}{content}{tooltip_html_close}'

    def set_field_infolist_label_classes(self, class_name: str):
        self._infolist_label_class_from_field = class_name
        return self

    def set_field_infolist_body_classes(self, class_name: str):
        self._infolist_body_class_from_field = class_name
        return self

    # --- Rendering ---
    def render(self):
        fields = self.schema()
        if isinstance(self.data, dict):
            data = [self.data]
        elif isinstance(self.data, DataKlass):
            data = [self.data.to_dict()]
        elif isinstance(self.data, list):
            data = self.data
        elif isinstance(self.data, ActiveRecord):
            data = [self.data.to_dict()]
        else:
            raise Exception(f'{self.data()} is not a valid data type')

        heading = self._heading(data) if callable(self._heading) else self._heading
        footer = self._footer(data) if callable(self._footer) else self._footer
        icon = self._icon(data) if callable(self._icon) else self._icon
        classes = self._container_class

        html = f"""
        <div class="{classes}" style="{self._style if hasattr(self, '_style') else ''}">
            {f'<div class="card-header bg-white {self._heading_class}"><i class="{icon} nav_icon"></i> {heading}</div>' if heading else ''}
            <div class="card-body">
        """

        # Render content
        if self._grid_mode:
            html += '<div class="row g-3">'
            col_class = f'col-{12 // self._grid_columns}'
            for record in data:
                record = DataKlass(record)
                for field in fields:
                    value = record.get(field.name(), "")
                    label = field.header()
                    label_text = label(value, record) if callable(label) else label
                    html += f"""
                        <div class="{col_class}">
                            <div class="fw-bold">{label_text}</div>
                            <div>{self.build_cell_content(field, value, record)}</div>
                        </div>
                    """
            html += '</div>'
        else:
            html += '<div class="row">'
            for record in data:
                for field in fields:
                    value = getattr(record, field.name(), "")

                    label = field.header()
                    label_text = label(value, record) if callable(label) else label
                    if isinstance(field._hidden, bool):
                        is_hidden = field._hidden
                    elif callable(field._hidden):
                        is_hidden = field._hidden(value, record)
                    if not is_hidden:
                        if getattr(field, '_is_separator', False):
                            html += "<div class='col-12'><hr class='my-3'></div>"
                            continue
                        html += f"<div class='infolist-label {field.get_label_classes() or self._infolist_label_class_from_field}'>{label_text}</div>"
                        html += f"<div class='infolist-body {field.class_name() or self._infolist_body_class_from_field}'>{self.build_cell_content(field, value, record)}</div>"
            html += '</div>'

        html += f"""
            </div>
            {f'<div class="card-footer text-muted {self._footer_class}">{footer}</div>' if footer else ''}
        </div>
        """
        return html

    def __str__(self) -> str:
        return self.render()

