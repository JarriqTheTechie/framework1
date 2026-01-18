from typing import Self

from markupsafe import Markup, escape

from framework1 import render_template_string_safe_internal
from framework1.core_services.Request import Request

from .fields import Field
from .master_detail import MasterDetailRow
from .utils import record_to_dict


class TableRenderMixin:
    def render(self) -> Markup:
        """Generate HTML for the table with improved configurability."""
        request = Request()
        fields = self.schema()

        def build_table_header(fields: list[Field]) -> list[str]:
            header = [f'<thead class="{self.thead_class}"><tr>']
            if getattr(self, "selectable"):
                header.append('<th class="text-center"><input type="checkbox" class="select-all"></th>')
            existing_fields = request.input(f"{self.table_name}[sort]", "").split(",")
            existing_dirs = request.input(f"{self.table_name}[sort_dir]", "").split(",")

            for field in fields:
                if isinstance(field, MasterDetailRow):
                    continue

                is_hidden = field._hidden if not callable(field._hidden) else False
                if is_hidden:
                    continue

                th_classes = field.class_name()
                content = field.header()

                if getattr(field, "_sortable", False):
                    if field.name() in existing_fields:
                        idx = existing_fields.index(field.name())
                        current_dir = existing_dirs[idx] if idx < len(existing_dirs) else "asc"
                        next_dir = "desc" if current_dir == "asc" else "asc"
                    else:
                        next_dir = "asc"

                    new_fields = existing_fields.copy()
                    new_dirs = existing_dirs.copy()

                    if field.name() in existing_fields:
                        idx = existing_fields.index(field.name())
                        new_dirs[idx] = next_dir
                    else:
                        new_fields.append(field.name())
                        new_dirs.append(next_dir)

                    query_args = request.all()
                    query_args[f"{self.table_name}[sort]"] = ",".join(new_fields)
                    query_args[f"{self.table_name}[sort_dir]"] = ",".join(new_dirs)

                    from urllib.parse import urlencode

                    sort_url = f"{request.path()}?{urlencode(query_args)}"

                    icon = ""
                    if field.name() in existing_fields:
                        idx = existing_fields.index(field.name())
                        dir_icon = existing_dirs[idx] if idx < len(existing_dirs) else "asc"
                        icon = f' <i class="ri-arrow-{"up-long-line" if dir_icon == "asc" else "down-long-line"}"></i>'

                    content = f'<a href="{sort_url}">{content}{icon}</a>'

                header.append(f'<th class="{th_classes}">{content}</th>')
            header.append("</tr></thead>")
            return header

        def build_cell_content(field: Field, value: str, record) -> str:
            if isinstance(field, MasterDetailRow):
                formatted_value = value
            else:
                formatted_value = field._format_value(value, record)

            record = record_to_dict(record)

            # Handle character limit
            if hasattr(field, "_limit") and field._limit is not None:
                limit_value = field._limit(record) if callable(field._limit) else field._limit
                if isinstance(limit_value, int) and len(str(formatted_value)) > limit_value:
                    formatted_value = str(formatted_value)[:limit_value] + field._limit_end

            # Handle word limit
            if hasattr(field, "_words_limit") and field._words_limit is not None:
                words_limit = field._words_limit(record) if callable(field._words_limit) else field._words_limit
                if isinstance(words_limit, int):
                    words = str(formatted_value).split()
                    if len(words) > words_limit:
                        formatted_value = " ".join(words[:words_limit]) + field._words_end

            # Handle HTML escaping
            if not getattr(field, "_render_html", False):
                formatted_value = escape(formatted_value)

            content_parts = []

            # Handle icon
            icon_classes = []
            if getattr(field, "_icon_map", None) and formatted_value in field._icon_map:
                icon_classes.append(field._icon_map[formatted_value])
            if getattr(field, "_icon", None):
                icon_classes.append(field._icon)
            if getattr(field, "_icon_color", None):
                icon_classes.append(field._icon_color)
            icon_html = f'<i class="{" ".join(icon_classes)}"></i>'
            if getattr(field, "_icon_position", "left") == "left":
                content_parts.append(f"{icon_html} ")
            else:
                content_parts.append(f" {icon_html}")

            # Add the main content
            content_parts.insert(1 if getattr(field, "_icon_position", "left") == "left" else 0, formatted_value)

            content = "".join(content_parts)

            # Add description if present
            if getattr(field, "_description", None):
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
                    if not field._description_is_html:
                        content += (
                            f'<div class="text-muted small">{escape(str(description_text)[:field._description_limit])}'
                            f"{field._description_limit_end}</div>"
                        )
                    else:
                        content += (
                            f'<div class="text-muted small">{Markup(description_text[:field._description_limit])}'
                            f"{field._description_limit_end}</div>"
                        )

            # Handle badge
            if getattr(field, "_badge", False):
                badge_classes = ["badge"]
                if getattr(field, "_badge_color_map", None) and formatted_value in field._badge_color_map:
                    badge_classes.append(f'bg-{field._badge_color_map[formatted_value]}')
                elif getattr(field, "_static_badge_color", None):
                    badge_classes.append(f'bg-{field._static_badge_color}')
                content = f'<span class="{" ".join(badge_classes)}">{content}</span>'

            # Handle URL
            if getattr(field, "_url_template", None):
                if callable(field._url_template):
                    url = field._url_template(record)
                else:
                    try:
                        url = field._url_template.format(record)
                    except KeyError:
                        url = "#"
                content = f'<a href="{url}">{content}</a>'

            tooltip_html_open = tooltip_html_close = ""
            tooltip_text = None

            if getattr(field, "_tooltip", None):
                tooltip = field._tooltip
                if callable(tooltip):
                    from inspect import signature

                    sig = signature(tooltip)
                    if len(sig.parameters) == 2:
                        tooltip_text = tooltip(record, record)
                    else:
                        tooltip_text = tooltip(record)
                else:
                    tooltip_text = tooltip

            if tooltip_text:
                tooltip_html_open = f'<span data-bs-toggle="tooltip" title="{escape(tooltip_text)}">'
                tooltip_html_close = "</span>"

            content = f"{tooltip_html_open}{content}{tooltip_html_close}"

            return content

        def build_table_body(data: list, fields: list[Field]) -> list[str]:
            body = [f'<tbody class="{self.tbody_class}">']
            has_default_actions = self.has_default_actions()
            has_custom_actions = self.has_custom_actions()
            has_master_detail = any(isinstance(field, MasterDetailRow) for field in fields)
            for record in data:
                record = record_to_dict(record)

                row_dbl_click_action_html = ""
                try:
                    row_dbl_click_action = self.record_url(record)
                    row_dbl_click_action_html = f' ondblclick="{row_dbl_click_action}"'
                except AttributeError:
                    pass

                row = [f'<tr class="{self.tr_class}" {row_dbl_click_action_html}>']
                if getattr(self, "selectable"):
                    row.append(
                        f'<td class="text-center"><input type="checkbox" class="row-select" value="{record.get(self.key_id)}"></td>'
                    )

                for field in fields:
                    if isinstance(field, MasterDetailRow):
                        continue

                    is_hidden = False
                    if callable(field._hidden):
                        is_hidden = field._hidden(record)
                    else:
                        is_hidden = field._hidden

                    if is_hidden:
                        continue

                    if "." in field.name():
                        # Support nested fields like "user.name"
                        parts = field.name().split(".")
                        value = record
                        for part in parts:
                            value = value.get(part, "")
                            if not value:
                                break
                    else:
                        value = record.get(field.name(), "")

                    content = build_cell_content(field, value, record)

                    # Build extra cell attributes
                    attr_dict = {}
                    if field._extra_cell_attributes:
                        if callable(field._extra_cell_attributes):
                            attr_dict = field._extra_cell_attributes(record)
                        else:
                            attr_dict = field._extra_cell_attributes

                    # Merge class names
                    base_class = field.class_name()
                    extra_class = attr_dict.pop("class", "")
                    combined_class = f"{base_class} {extra_class}".strip()

                    # Build other attribute string, escape values for safety
                    attr_str = " ".join(f'{k}="{escape(v)}"' for k, v in attr_dict.items())
                    if field.name() == fields[0].name():
                        collapse_toggle = ""
                        if has_master_detail and getattr(self, "master_detail_expandable", None):
                            collapse_toggle = (
                                f'<button class="collapse-caret" type="button" data-bs-toggle="collapse" '
                                f'data-bs-target=".collapse-contentId-{record.get(self.key_id)}" '
                                f'aria-expanded="false" aria-controls="contentId-{record.get(self.key_id)}">'
                                ' <i class="ri-arrow-right-s-line icon-collapsed"></i>'
                                ' <i class="ri-arrow-down-s-line icon-expanded"></i> </button>'
                            )
                        row.append(
                            f'<td data-framework1-field-name="{field.name()}" class="{combined_class}" {attr_str}>{collapse_toggle} {content}</td>'
                        )
                    else:
                        row.append(
                            f'<td data-framework1-field-name="{field.name()}" class="{combined_class}" {attr_str}>{content}</td>'
                        )

                if has_default_actions and has_custom_actions:
                    row.append(f'<td data-framework1-field-name="" class="">Delete {record_data}</td>')
                    row.append(self.get_custom_actions(record_data))

                row.append("</tr>")
                body.extend(row)

                # --- MASTER DETAIL SUPPORT ---
                if getattr(self, "master_detail_expandable", None):
                    for row in fields:
                        if isinstance(row, MasterDetailRow):
                            # update record with data from row.set_data()
                            data_from_row = row.data
                            if callable(data_from_row):
                                record.update(data_from_row(record))
                            else:
                                record.update(row.data)

                            if getattr(row, "_template", None):
                                if callable(row._template):
                                    master_detail_view_template = row._template(record)
                                else:
                                    master_detail_view_template = row._template
                                body.append(
                                    f"""
                                    <tr class="master-detail-row collapse collapse-contentId-{record.get(self.key_id)}">
                                        <td colspan="{len(fields) + (1 if getattr(self, 'selectable', False) else 0)}">
                                            <div class="collapse collapse-contentId-{record.get(self.key_id)}">
                                                {master_detail_view_template}
                                            </div>
                                        </td>
                                    </tr>
                                    """
                                )
                                break

            body.append("</tbody>")
            return body

        def build_pagination() -> list[str]:
            if not (pagination := getattr(self, "pagination", None)):
                return []

            if not hasattr(pagination, "items"):
                return []

            total = pagination.total
            current_page = pagination.current_page
            last_page = pagination.last_page

            return [
                render_template_string_safe_internal(
                    "table-dsl/pagination.html",
                    total=total,
                    data=self.data,
                    current_page=current_page,
                    last_page=last_page,
                    per_page=pagination.per_page,
                    table_name=self.__class__.__name__,
                    request=request,
                )
            ]

        # Main table assembly
        html = [
            '<div class="table-responsive">',
            f'<table id="{self.__class__.__name__}" class="{self.table_class}" style="{self.table_style if getattr(self, "table_style", "") else ""}">',
        ]

        search_session_key = f"{self.__class__.__name__}_search"
        search_value = escape(Request().input("search", request.session().get(search_session_key, "")))
        search_placeholder = self.search_placeholder

        table_actions_header = []

        if not bool(self.sub_resource_table):
            table_actions_header.insert(
                0,
                render_template_string_safe_internal(
                    "table-dsl/search.html",
                    search_value=search_value,
                    search_placeholder=search_placeholder,
                ),
            )

        if getattr(self, "model", None) and getattr(self.model, "__exportable__", False):
            query_args = request.all()
            query_args["table"] = self.__class__.__name__
            export_url = f"/f1/export-excel?{__import__('urllib.parse').parse.urlencode(query_args)}"
            table_actions_header.append(
                f'<a class="btn btn-outline-secondary btn-sm ms-2" href="{export_url}">Export</a>'
            )

        html.insert(
            0,
            f"<div class='table-actions d-inline-flex my-3 justify-content-end'>{''.join(table_actions_header)}</div>",
        )

        html.extend(build_table_header(fields))

        if self.data:
            html.extend(build_table_body(self.data, fields))

        html.append("</table>")
        html.extend(build_pagination())
        html.append("</div>")

        from framework1.dsl.F1TableFilterForm import F1TableFilterForm

        if len(self.filterable_fields) != 0:
            filter_form = F1TableFilterForm(request.all()).set_resource_from_table(self)
            filter_bar_css = render_template_string_safe_internal("table-dsl/filter-bar-styles.html")
            filter_bar = render_template_string_safe_internal(
                "table-dsl/filter-bar.html", filter_form=filter_form, filter_bar_css=filter_bar_css
            )
            html.insert(1, filter_bar)

        return Markup("\n".join(html))

    def __str__(self) -> Self:
        """Return HTML when the object is converted to a string."""
        return self.render()
