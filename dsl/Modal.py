from typing import Self, Dict, Any, Union
from markupsafe import Markup, escape
from framework1 import render_template_string_safe_external, render_template_string_safe_internal
from flask import render_template_string

class _ModalBase:
    def __init__(self, modal_id: str, context: Dict[str, Any] = None):
        self.modal_size = ""
        self.modal_id = modal_id
        self.modal_title = ""
        self.modal_body = ""
        self.modal_footer_buttons = []
        self.is_static = ""
        self.context = context or {}

        # trigger button config
        self.trigger_label = "Open"
        self.trigger_class = "btn btn-primary"
        self.trigger_icon = ""

    def title(self, text: str) -> Self:
        self.modal_title = text
        return self

    def body(self, content: Union[str, Markup],
             is_template: bool = False,
             use_internal: bool = False,
             inline_template: bool = False) -> Self:
        """
        - Raw string → escaped
        - Markup → trusted
        - Template path → uses safe renderer (internal/external)
        - Inline Jinja string → rendered directly with context
        """
        if isinstance(content, Markup):
            self.modal_body = content

        elif inline_template:
            self.modal_body = Markup(
                render_template_string(content, **self.context)
            )

        elif is_template:
            if use_internal:
                self.modal_body = Markup(
                    render_template_string_safe_internal(content, **self.context)
                )
            else:
                self.modal_body = Markup(
                    render_template_string_safe_external(content, **self.context)
                )

        else:
            self.modal_body = escape(content)

        return self

    def footer_buttons(self, buttons) -> Self:
        self.modal_footer_buttons = buttons
        return self

    def trigger_button(self, label: str = "Open",
                       btn_class: str = "btn btn-primary",
                       icon: str = "",
                       trigger_type: str = "button") -> Self:
        """
        Configure trigger.
        trigger_type = 'button' (default) or 'link'
        """
        self.trigger_label = label
        self.trigger_class = btn_class
        self.trigger_icon = icon
        self.trigger_type = trigger_type
        return self

    def close_modal_by_clicking_away(self, close_modal=True) -> Self:
        if not close_modal:
            self.is_static = 'data-bs-backdrop="static"'
        return self

    def _render_trigger(self, target_type: str) -> str:
        icon_html = f"{self.trigger_icon} " if self.trigger_icon else ""
        if self.trigger_type == "link":
            return f"""
<a href="#{self.modal_id}" class="{self.trigger_class}" 
   data-bs-toggle="{target_type}" role="button">
   {icon_html}{self.trigger_label}
</a>
"""
        else:  # default button
            return f"""
<button class="{self.trigger_class}" type="button" 
        data-bs-toggle="{target_type}" data-bs-target="#{self.modal_id}">
  {icon_html}{self.trigger_label}
</button>
"""


# ---------------- Standard Modal ---------------- #

class Modal(_ModalBase):
    def modal_lg(self) -> Self: self.modal_size = "modal-lg"; return self
    def modal_sm(self) -> Self: self.modal_size = "modal-sm"; return self
    def modal_md(self) -> Self: self.modal_size = "modal-md"; return self
    def modal_xl(self) -> Self: self.modal_size = "modal-xl"; return self
    def modal_fullscreen(self) -> Self: self.modal_size = "modal-fullscreen"; return self

    def render(self) -> Markup:
        trigger_html = self._render_trigger("modal")
        footer_html = "\n        ".join(button.render() for button in self.modal_footer_buttons)
        modal_html = f"""
<div id="{self.modal_id}" class="modal fade" tabindex="-1" {self.is_static}>
  <div class="modal-dialog {self.modal_size}">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">{self.modal_title}</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        {self.modal_body}
      </div>
      <div class="modal-footer">
        {footer_html}
      </div>
    </div>
  </div>
</div>
"""
        return Markup(trigger_html + modal_html)

    def __str__(self):
        return self.render()


# ---------------- Slide-Over Modal ---------------- #

class ModalSlideOver(_ModalBase):
    def modal_lg(self) -> Self: self.modal_size = "offcanvas-lg"; return self
    def modal_sm(self) -> Self: self.modal_size = "offcanvas-sm"; return self
    def modal_md(self) -> Self: self.modal_size = "offcanvas-md"; return self
    def modal_xl(self) -> Self: self.modal_size = "offcanvas-xl"; return self
    def modal_fullscreen(self) -> Self: self.modal_size = "offcanvas-xxl"; return self

    def render(self) -> Markup:
        trigger_html = self._render_trigger("offcanvas")
        footer_html = "\n        ".join(button.render() for button in self.modal_footer_buttons)
        modal_html = f"""
<div id="{self.modal_id}" class="offcanvas offcanvas-end {self.modal_size}" tabindex="-1" {self.is_static}>
  <div class="offcanvas-header">
    <h5 class="offcanvas-title">{self.modal_title}</h5>
    <button type="button" class="btn-close" data-bs-dismiss="offcanvas" aria-label="Close"></button>
  </div>
  <div class="offcanvas-body">
    {self.modal_body}
  </div>
  <div class="offcanvas-footer">
    {footer_html}
  </div>
</div>
"""
        return Markup(trigger_html + modal_html)

    def __str__(self):
        return self.render()
