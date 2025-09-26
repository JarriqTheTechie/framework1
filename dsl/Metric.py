from markupsafe import Markup, escape
from typing import Union


class Metric:
    def __init__(self, name: str, value: Union[str, int, float],
                 description: str = None,
                 icon: str = None,
                 color: str = None,
                 data: Union[dict, object] = None):
        self.name = name
        self.value = value
        self.description = description
        self.icon = icon
        self.color = color

        # Optional configs
        self._url = None
        self._badge = False
        self._delta = None
        self._delta_color = None
        self._chart = None
        self._profile = None
        self._grouped = []

        # --- CSS classes ---
        self._container_class = "metric-card text-center p-3"
        self._icon_class = ""
        self._value_class = "metric-value fw-bold fs-4"
        self._label_class = "metric-label text-muted"
        self._delta_class = ""

        # --- Extra attributes ---
        self._extra_attributes = {}
        self._extra_value_attributes = {}

        self._raw_html = None
        self._template_path = None
        self._template_context = {}
        self._template_inline = False

        self.data = data or {}

        self._icon_bg = "bg-light"  # default background
        self._icon_extra_class = ""  # extra classes for the <i> tag

    # --- DSL methods ---

    def with_icon(self, icon: str, color: str = None):
        self.icon = icon
        self.color = color
        return self

    def icon_background(self, bg_class: str):
        """
        Set background color class for the icon box.
        Example: .icon_background("bg-primary") or .icon_background("bg-warning-subtle")
        """
        self._icon_bg = bg_class
        return self

    def icon_classes(self, classes: str, include_default=True):
        """
        Add custom classes to the <i> icon itself (e.g., size, animations).
        Example: .icon_classes("fs-3") or .icon_classes("ri-2x")
        """
        if include_default:
            self._icon_extra_class = f"{self._icon_extra_class} {classes}".strip()
        else:
            self._icon_extra_class = classes.strip()
        return self

    def with_url(self, url: str):
        self._url = url
        return self

    def badge(self, enable=True):
        self._badge = enable
        return self

    def delta(self, value: str, color: str = None):
        """Show change indicator e.g. +3.5%"""
        self._delta = value
        self._delta_color = color
        return self

    def profile(self, avatar_url: str, subtitle: str,
                link_text: str = None, link_url: str = None):
        """Profile style metric card"""
        self._profile = {
            "avatar": avatar_url,
            "subtitle": subtitle,
            "link_text": link_text,
            "link_url": link_url
        }
        return self

    def chart(self, dataset: list[float], labels: list[str]):
        """Attach a mini chart or timeseries"""
        self._chart = {"data": dataset, "labels": labels}
        return self

    def group(self, *metrics):
        """Group multiple metrics horizontally"""
        self._grouped.extend(metrics)
        return self

    # --- Class mutators ---
    def container_classes(self, classes: str, include_default=True):
        self._container_class = f"{self._container_class} {classes}" if include_default else classes
        return self

    def value_classes(self, classes: str, include_default=True):
        self._value_class = f"{self._value_class} {classes}" if include_default else classes
        return self

    def label_classes(self, classes: str, include_default=True):
        self._label_class = f"{self._label_class} {classes}" if include_default else classes
        return self

    def delta_classes(self, classes: str, include_default=True):
        self._delta_class = f"{self._delta_class} {classes}" if include_default else classes
        return self

    def extra_attributes(self, attrs: Union[dict, callable]):
        """
        Set additional HTML attributes for the outer container.
        Supports static dict or callable(record) -> dict
        """
        self._extra_attributes = attrs
        return self

    def extra_value_attributes(self, attrs: Union[dict, callable]):
        """
        Set additional HTML attributes for the value element.
        Supports static dict or callable(record) -> dict
        """
        self._extra_value_attributes = attrs
        return self

    def raw_html(self, html: str):
        """
        Directly set raw HTML as the metric content.
        Overrides normal rendering.
        """
        self._raw_html = html
        return self

    def template(self, template_or_str: str, context: dict = None, inline: bool = False):
        """
        Render metric from either:
        - a template path (default)
        - an inline Jinja template string (inline=True)

        Built-in context:
            {{ name }}  -> metric name
            {{ value }} -> metric value
            {{ data }}  -> metric.data (dict, to_dict(), or vars())
        """
        base_context = {
            "name": self.name,
            "value": self.value,
            "data": self._resolve_data(),
        }
        merged_context = {**base_context, **(context or {})}

        self._template_path = template_or_str
        self._template_context = merged_context
        self._template_inline = inline
        return self

    def _resolve_data(self):
        """Resolve self.data into a dictionary-like structure."""
        resolved = self.data

        # If callable, evaluate
        if callable(resolved):
            try:
                resolved = resolved()
            except Exception:
                return {}

        # If ActiveRecord or DataKlass → convert
        try:
            from framework1.database.ActiveRecord import ActiveRecord
            from framework1.utilities.DataKlass import DataKlass
            if isinstance(resolved, (ActiveRecord, DataKlass)):
                return resolved.to_dict()
        except ImportError:
            pass

        # If dict already → return as-is
        if isinstance(resolved, dict):
            return resolved

        # If generic object → try vars()
        try:
            return vars(resolved)
        except Exception:
            return {}

    # --- Rendering ---
    def render(self):
        # --- Resolve data ---
        resolved_data = self._resolve_data()

        # --- Raw HTML rendering ---
        if self._raw_html:
            return Markup(self._raw_html)

        # --- Template rendering ---
        if self._template_path:
            try:
                context = {**self._template_context,
                           "data": resolved_data,
                           "name": self.name,
                           "value": self.value}
                if getattr(self, "_template_inline", False):
                    from jinja2 import Template
                    return Markup(Template(self._template_path).render(**context))
                else:
                    from framework1 import render_template_string_safe_internal
                    return Markup(render_template_string_safe_internal(
                        self._template_path, **context
                    ))
            except Exception as e:
                return Markup(f"<!-- Failed to render template: {escape(str(e))} -->")

        # --- Profile card rendering ---
        if self._profile:
            return Markup(f"""
                <div class="card p-3 d-flex flex-row align-items-center {escape(self._container_class)}" {self._render_attrs(self._extra_attributes)}>
                    <img src="{escape(self._profile['avatar'])}" class="rounded-circle me-3" width="80">
                    <div>
                        <h5 class="mb-0">{escape(self.value)}</h5>
                        <div class="text-muted">{escape(self._profile.get('subtitle', ''))}</div>
                        {f'<a href="{escape(self._profile["link_url"])}">{escape(self._profile.get("link_text", ""))}</a>' if self._profile.get("link_url") else ''}
                    </div>
                </div>
            """)

        # --- Default metric card ---
        icon_html = ""
        if self.icon:
            color_class = f"text-{escape(self.color)}" if self.color else ""
            icon_html = f'<i class="{escape(self.icon)} {color_class} {self._icon_class.strip()} me-1"></i>'

        delta_html = ""
        if self._delta:
            delta_color = f"text-{self._delta_color}" if self._delta_color else ""
            delta_html = f'<span class="{self._delta_class.strip()} {delta_color}">{escape(self._delta)}</span>'

        # pull description from data if not explicitly set
        description_text = self.description or resolved_data.get("description") or ""
        subtitle_text = resolved_data.get("subtitle") or ""
        note_text = resolved_data.get("note") or ""

        extra_html = ""
        if description_text:
            extra_html += f'<div class="text-muted small">{escape(description_text)}</div>'
        if subtitle_text:
            extra_html += f'<div class="text-secondary small">{escape(subtitle_text)}</div>'
        if note_text:
            extra_html += f'<div class="text-info small">{escape(note_text)}</div>'

        card_html = f"""
        <div class="{self._container_class}" {self._render_attrs(self._extra_attributes)}>
            {icon_html}
            <div class="{self._value_class}" {self._render_attrs(self._extra_value_attributes)}>{escape(str(self.value))}{delta_html}</div>
            <div class="{self._label_class}">{escape(self.name)}</div>
            {extra_html}
        </div>
        """

        # --- Grouped metrics styled like dashboard row ---
        if self._grouped:
            items_html = []
            total = len(self._grouped)
            for i, m in enumerate(self._grouped):
                # icon box
                icon_html = ""
                if m.icon:
                    icon_html = f"""
                        <div class="d-inline-flex align-items-center justify-content-center rounded p-2 me-2 {escape(m._icon_bg)}">
                            <i class="{escape(m.icon)} {m._icon_extra_class} text-{escape(m.color) if m.color else 'secondary'}"></i>
                        </div>
                    """

                # metric content
                item_html = f"""
                <div class="d-flex flex-column align-items-start text-start flex-fill">
                    {icon_html}
                    <div class="metric-label text-muted small">{escape(m.name)}</div>
                    <div class="metric-value fw-bold">{escape(str(m.value))}</div>
                </div>
                """

                # divider between items
                if i < total - 1:
                    item_html += '<div class="vr mx-3 text-muted opacity-25"></div>'

                items_html.append(item_html)

            return Markup(
                f"""
                <div class="{escape(self._container_class)}" {self._render_attrs(self._extra_attributes)}>
                    <div class="d-flex justify-content-around align-items-center">
                        {''.join(items_html)}
                    </div>
                </div>
                """
            )
        # --- fallback ---
        return Markup(card_html)

    def _render_attrs(self, attrs, record=None):
        """Helper for attribute dict/callable resolution."""
        if callable(attrs):
            try:
                attrs = attrs(record)
            except Exception:
                attrs = {}
        if not isinstance(attrs, dict):
            return ""
        return " ".join(f'{escape(k)}="{escape(v)}"' for k, v in attrs.items())

    def __str__(self):
        return self.render()
