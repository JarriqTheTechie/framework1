from typing import Self

from markupsafe import Markup, escape

from framework1 import render_template_string_safe_internal, profile_component
from framework1.core_services.Request import Request

from .actions import TableAction
from .fields import Field
from .master_detail import MasterDetailRow
from .utils import record_to_dict


class TableRenderMixin:
    def render(self) -> Markup:
        """Generate HTML for the table with improved configurability."""
        request = Request()
        fields = self._get_schema_cached()
        callable_arity_cache = {}

        def callable_arity(fn) -> int:
            arity = callable_arity_cache.get(fn)
            if arity is not None:
                return arity
            try:
                from inspect import signature
                arity = len(signature(fn).parameters)
            except Exception:
                arity = 1
            callable_arity_cache[fn] = arity
            return arity

        def resolve_visible_fields(fields: list[Field]):
            """Apply toggleable column preferences + hidden flags."""
            session = request.session()
            toggleables = [f for f in fields if getattr(f, "_toggleable", False)]

            raw = request.input(f"{self.table_name}[columns]", None)
            chosen = [c.strip() for c in raw.split(",") if c.strip()] if raw else None

            if chosen is None and getattr(self, "persist_columns", False):
                chosen = session.get(f"{self.table_name}_columns", None)
                if isinstance(chosen, str):
                    chosen = [c for c in chosen.split(",") if c]

            if getattr(self, "persist_columns", False) and chosen is not None:
                session[f"{self.table_name}_columns"] = chosen

            def is_visible(field: Field, record=None):
                # honor explicit hidden
                hidden = field._hidden(record) if callable(getattr(field, "_hidden", None)) and record else field._hidden
                if hidden:
                    return False
                if getattr(field, "_toggleable", False):
                    if chosen is not None:
                        return field.name() in chosen
                    return getattr(field, "_default_visible", True)
                return True

            visible_fields = [f for f in fields if is_visible(f)]
            visible_names = [f.name() for f in visible_fields]
            return visible_fields, toggleables, visible_names

        with profile_component(f"{self.table_name}.resolve_visible_fields", kind="table"):
            fields, toggleable_fields, visible_field_names = resolve_visible_fields(fields)

        has_row_actions = hasattr(self, "has_custom_actions") and self.has_custom_actions()

        def build_table_header(fields: list[Field]) -> list[str]:
            from urllib.parse import urlencode

            header = [f'<thead class="{self.thead_class}"><tr>']
            if getattr(self, "selectable"):
                header.append('<th class="text-center"><input type="checkbox" class="select-all"></th>')
            existing_fields = [f for f in request.input(f"{self.table_name}[sort]", "").split(",") if f]
            existing_dirs = request.input(f"{self.table_name}[sort_dir]", "").split(",")
            sort_index = {name: idx for idx, name in enumerate(existing_fields)}
            sort_dir_by_field = {
                name: (existing_dirs[idx] if idx < len(existing_dirs) and existing_dirs[idx] else "asc")
                for name, idx in sort_index.items()
            }
            base_query_args = request.all()
            base_path = request.path()

            for field in fields:
                if isinstance(field, MasterDetailRow):
                    continue

                is_hidden = field._hidden if not callable(field._hidden) else False
                if is_hidden:
                    continue

                th_classes = field.class_name()
                content = field.header()
                field_name = field.name()

                if getattr(field, "_sortable", False):
                    existing_idx = sort_index.get(field_name)
                    if existing_idx is not None:
                        current_dir = sort_dir_by_field.get(field_name, "asc")
                        next_dir = "desc" if current_dir == "asc" else "asc"
                    else:
                        next_dir = "asc"

                    new_fields = existing_fields.copy()
                    new_dirs = existing_dirs.copy()

                    if existing_idx is not None:
                        new_dirs[existing_idx] = next_dir
                    else:
                        new_fields.append(field_name)
                        new_dirs.append(next_dir)

                    query_args = dict(base_query_args)
                    query_args[f"{self.table_name}[sort]"] = ",".join(new_fields)
                    query_args[f"{self.table_name}[sort_dir]"] = ",".join(new_dirs)
                    sort_url = f"{base_path}?{urlencode(query_args)}"

                    icon = ""
                    if existing_idx is not None:
                        dir_icon = sort_dir_by_field.get(field_name, "asc")
                        icon = f' <i class="ri-arrow-{"up-long-line" if dir_icon == "asc" else "down-long-line"}"></i>'

                    content = f'<a href="{sort_url}">{content}{icon}</a>'

                header.append(f'<th class="{th_classes}">{content}</th>')
            if has_row_actions:
                header.append('<th class="text-end">Actions</th>')
            header.append("</tr></thead>")
            return header

        def build_cell_content(field: Field, value: str, record) -> str:
            if isinstance(field, MasterDetailRow):
                formatted_value = value
            else:
                formatted_value = field._format_value(value, record)

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

            # Ensure downstream render logic always works with string-like values
            if formatted_value is None:
                formatted_value = ""
            elif not isinstance(formatted_value, (str, Markup)):
                formatted_value = str(formatted_value)

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
                    if callable_arity(field._description) == 2:
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
                    if callable_arity(tooltip) == 2:
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
            has_master_detail = any(isinstance(field, MasterDetailRow) for field in fields)
            first_field_name = fields[0].name() if fields else None
            field_specs = []
            for field in fields:
                if isinstance(field, MasterDetailRow):
                    continue
                field_name = field.name()
                field_specs.append({
                    "field": field,
                    "name": field_name,
                    "parts": field_name.split(".") if "." in field_name else None,
                    "base_class": field.class_name(),
                    "is_first": field_name == first_field_name,
                })
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

                for spec in field_specs:
                    field = spec["field"]
                    field_name = spec["name"]

                    is_hidden = False
                    if callable(field._hidden):
                        is_hidden = field._hidden(record)
                    else:
                        is_hidden = field._hidden

                    if is_hidden:
                        continue

                    if spec["parts"]:
                        # Support nested fields like "user.name"
                        value = record
                        for part in spec["parts"]:
                            value = value.get(part, "")
                            if not value:
                                break
                    else:
                        value = record.get(field_name, "")

                    content = build_cell_content(field, value, record)

                    # Build extra cell attributes
                    attr_dict = {}
                    if field._extra_cell_attributes:
                        if callable(field._extra_cell_attributes):
                            attr_dict = field._extra_cell_attributes(record)
                        else:
                            attr_dict = dict(field._extra_cell_attributes)

                    # Merge class names
                    base_class = spec["base_class"]
                    extra_class = attr_dict.pop("class", "")
                    combined_class = f"{base_class} {extra_class}".strip()

                    # Build other attribute string, escape values for safety
                    attr_str = " ".join(f'{k}="{escape(v)}"' for k, v in attr_dict.items())
                    if spec["is_first"]:
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
                            f'<td data-framework1-field-name="{field_name}" class="{combined_class}" {attr_str}>{collapse_toggle} {content}</td>'
                        )
                    else:
                        row.append(
                            f'<td data-framework1-field-name="{field_name}" class="{combined_class}" {attr_str}>{content}</td>'
                        )

                if has_row_actions:
                    actions_html = []
                    try:
                        row_actions = self.get_custom_actions(record)
                    except Exception:
                        row_actions = []
                    for action in row_actions or []:
                        if isinstance(action, TableAction):
                            actions_html.append(action.render(record, record.get(self.key_id)))
                        else:
                            actions_html.append(str(action))
                    row.append(f'<td class="table-actions text-end">{" ".join(actions_html)}</td>')

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

            if getattr(pagination, "mode", None) == "keyset":
                return [
                    render_template_string_safe_internal(
                        "table-dsl/pagination-keyset.html",
                        data=self.data,
                        has_next=getattr(pagination, "has_next", False),
                        next_cursor=getattr(pagination, "next_cursor", None),
                        current_cursor=getattr(pagination, "current_cursor", None),
                        cursor_param=getattr(pagination, "cursor_param", "cursor"),
                        table_name=self.__class__.__name__,
                        request=request,
                    )
                ]
            if getattr(pagination, "mode", None) == "simple":
                current_page = getattr(pagination, "current_page", 1)
                has_prev = getattr(pagination, "has_prev", False)
                has_next = getattr(pagination, "has_next", False)
                prev_href = request.clean_table_url(self.__class__.__name__, {"page": current_page - 1}) if has_prev else "#"
                next_href = request.clean_table_url(self.__class__.__name__, {"page": current_page + 1}) if has_next else "#"
                return [
                    f"""
                    <nav aria-label="Simple pagination" class="mt-3">
                        <div class="d-flex align-items-center justify-content-between">
                            <div class="pagination-info">
                                Showing {len(self.data)} items
                            </div>
                            <ul class="pagination mb-0">
                                <li class="page-item {"disabled" if not has_prev else ""}">
                                    <a class="page-link" href="{prev_href}" {"tabindex='-1'" if not has_prev else ""}>
                                        Previous
                                    </a>
                                </li>
                                <li class="page-item {"disabled" if not has_next else ""}">
                                    <a class="page-link" href="{next_href}" {"tabindex='-1'" if not has_next else ""}>
                                        Next
                                    </a>
                                </li>
                            </ul>
                        </div>
                    </nav>
                    """
                ]

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
        search_value = escape(request.input("search", request.session().get(search_session_key, "")))
        search_placeholder = self.search_placeholder

        table_actions_header = []
        header_actions = []
        if hasattr(self, "has_header_actions") and self.has_header_actions():
            try:
                header_actions = self.get_header_actions() or []
            except Exception:
                header_actions = []
        bulk_actions = []
        if hasattr(self, "has_bulk_actions") and self.has_bulk_actions():
            try:
                bulk_actions = [a for a in (self.get_bulk_actions() or []) if getattr(a, "scope", "row") == "bulk"]
            except Exception:
                bulk_actions = []

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
            export_url = f"/f1/export-csv-chunked?{__import__('urllib.parse').parse.urlencode(query_args)}"
            table_actions_header.append(
                f'<a class="btn btn-outline-secondary btn-sm ms-2" href="{export_url}">Export CSV</a>'
            )

        # Header actions (non-bulk)
        for action in header_actions:
            if isinstance(action, TableAction) and getattr(action, "scope", "row") == "header":
                table_actions_header.append(action.render({}))

        # Column visibility picker
        if toggleable_fields:
            checkbox_rows = []
            for f in toggleable_fields:
                checked = "checked" if f.name() in visible_field_names or getattr(f, "_default_visible", True) else ""
                checkbox_rows.append(
                    f'<div class="form-check">'
                    f'<input class="form-check-input" type="checkbox" value="{escape(f.name())}" id="{self.table_name}_col_{escape(f.name())}" {checked}>'
                    f'<label class="form-check-label" for="{self.table_name}_col_{escape(f.name())}">{escape(f.header())}</label>'
                    f"</div>"
                )

            column_picker_html = f"""
            <div class="dropdown ms-2">
              <button class="btn btn-outline-secondary btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
                Columns
              </button>
              <div class="dropdown-menu p-3" style="min-width: 220px;">
                <form id="{self.table_name}_column_form" method="get">
                  <input type="hidden" name="{self.table_name}[columns]" id="{self.table_name}_columns_input">
                  {''.join(checkbox_rows)}
                  <button type="submit" class="btn btn-primary btn-sm mt-2 w-100">Apply</button>
                </form>
              </div>
            </div>
            <script>
            (function() {{
              var form = document.getElementById("{self.table_name}_column_form");
              if (!form) return;
              var hidden = document.getElementById("{self.table_name}_columns_input");
              var checks = form.querySelectorAll('input[type="checkbox"]');
              function sync() {{
                hidden.value = Array.prototype.slice.call(checks).filter(function(c) {{ return c.checked; }}).map(function(c) {{ return c.value; }}).join(',');
              }}
              checks.forEach(function(c) {{ c.addEventListener('change', sync); }});
              sync();
            }})();
            </script>
            """
            table_actions_header.append(column_picker_html)

        # Bulk actions dropdown (requires selectable checkboxes)
        if bulk_actions and getattr(self, "selectable"):
            bulk_buttons = []
            for action in bulk_actions:
                action_url = action._resolve_url({})
                confirm_attr = f" data-confirm=\"{escape(action.confirm)}\"" if getattr(action, 'confirm', None) else ""
                bulk_buttons.append(
                    f'<button type="button" class="dropdown-item bulk-action-btn" data-url="{escape(action_url)}" '
                    f'data-method="{escape(action.method)}"{confirm_attr}>{escape(action.label)}</button>'
                )
            bulk_html = f"""
            <div class="dropdown ms-2">
              <button class="btn btn-outline-secondary btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
                Bulk Actions
              </button>
              <div class="dropdown-menu">
                {''.join(bulk_buttons)}
              </div>
            </div>
            <form id="{self.table_name}_bulk_form" method="post" class="d-none"></form>
            <script>
            (function() {{
              var form = document.getElementById("{self.table_name}_bulk_form");
              var table = document.getElementById("{self.table_name}");
              if (!table) return;
              function checkboxes() {{ return table.querySelectorAll('.row-select'); }}
              function selectedIds() {{
                return Array.prototype.slice.call(checkboxes()).filter(function(c) {{ return c.checked; }}).map(function(c) {{ return c.value; }});
              }}
              (table.closest('.table-responsive') || document).querySelectorAll('.bulk-action-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                  var ids = selectedIds();
                  if (!ids.length) return alert('Select at least one row.');
                  var confirmText = btn.getAttribute('data-confirm');
                  if (confirmText && !window.confirm(confirmText)) return;
                  // clear previous
                  form.innerHTML = '';
                  var idsInput = document.createElement('input');
                  idsInput.type = 'hidden';
                  idsInput.name = 'ids';
                  idsInput.value = ids.join(',');
                  form.appendChild(idsInput);
                  var methodInput = document.createElement('input');
                  methodInput.type = 'hidden';
                  methodInput.name = '_method';
                  methodInput.value = (btn.getAttribute('data-method') || 'POST').toUpperCase();
                  form.appendChild(methodInput);
                  form.action = btn.getAttribute('data-url');
                  form.method = 'post';
                  form.submit();
                }});
              }});
            }})();
            </script>
            """
            table_actions_header.append(bulk_html)

        html.insert(
            0,
            f"<div class='table-actions d-inline-flex my-3 justify-content-end'>{''.join(table_actions_header)}</div>",
        )

        with profile_component(f"{self.table_name}.build_table_header", kind="table"):
            html.extend(build_table_header(fields))

        with profile_component(f"{self.table_name}.load_data", kind="table"):
            data = self._ensure_data_loaded()
        if data:
            with profile_component(f"{self.table_name}.build_table_body", kind="table"):
                html.extend(build_table_body(data, fields))

        html.append("</table>")
        with profile_component(f"{self.table_name}.build_pagination", kind="table"):
            html.extend(build_pagination())
        html.append("</div>")

        if getattr(self, "selectable", False):
            html.append(
                f"""
                <script>
                (function() {{
                  var table = document.getElementById("{self.__class__.__name__}");
                  if (!table) return;
                  var selectAll = table.querySelector('.select-all');
                  var rows = function() {{ return table.querySelectorAll('.row-select'); }};
                  function syncSelectAll() {{
                    if (!selectAll) return;
                    var boxes = Array.prototype.slice.call(rows());
                    if (!boxes.length) return;
                    var allChecked = boxes.every(function(c) {{ return c.checked; }});
                    var anyChecked = boxes.some(function(c) {{ return c.checked; }});
                    selectAll.indeterminate = !allChecked && anyChecked;
                    selectAll.checked = allChecked;
                  }}
                  if (selectAll) {{
                    selectAll.addEventListener('change', function() {{
                      var checked = selectAll.checked;
                      rows().forEach(function(c) {{ c.checked = checked; }});
                      syncSelectAll();
                    }});
                  }}
                  rows().forEach(function(c) {{
                    c.addEventListener('change', syncSelectAll);
                  }});
                  syncSelectAll();
                }})();
                </script>
                """
            )

        from framework1.dsl.F1TableFilterForm import F1TableFilterForm

        if len(self.filterable_fields) != 0:
            with profile_component(f"{self.table_name}.build_filter_bar", kind="table"):
                filter_form = F1TableFilterForm(request.all()).set_resource_from_table(self)
                filter_bar_css = render_template_string_safe_internal("table-dsl/filter-bar-styles.html")
                filter_bar = render_template_string_safe_internal(
                    "table-dsl/filter-bar.html", filter_form=filter_form, filter_bar_css=filter_bar_css
                )
                html.insert(1, filter_bar)

        with profile_component(f"{self.table_name}.render_markup_join", kind="table"):
            return Markup("\n".join(html))

    def __str__(self) -> Self:
        """Return HTML when the object is converted to a string."""
        return self.render()
