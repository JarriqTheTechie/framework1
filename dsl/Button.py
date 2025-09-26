from typing import Literal, Self

from markupsafe import Markup

from framework1.dsl.Modal import Modal, ModalSlideOver


class Button:
    def __init__(self, button_id):
        self.button_id = button_id
        self.button_label = ""
        self.button_classes = ""
        self.js_action_code = ""
        self.extra_attrs = {}

    def label(self, text):
        self.button_label = text
        return self

    def classes(self, class_name):
        self.button_classes = class_name
        return self

    def js_action(self, js_code):
        self.js_action_code = js_code
        return self

    def extra_attributes(self, attrs: dict):
        self.extra_attrs = attrs
        return self

    def render(self) -> Markup | Self:
        # Build the extra attributes
        extra_attrs_str = " ".join(f'{key}="{value}"' for key, value in self.extra_attrs.items())
        js_action_str = f"""
        onclick='{self.js_action_code}'
        """ if self.js_action_code else ""
        return Markup(
            f'<button id="{self.button_id}" type="button" class=" mb-3 {self.button_classes}" {js_action_str} {extra_attrs_str}>{self.button_label}</button>')

    def __str__(self):
        return self.render()


class ModalButton(Button):
    def __init__(self, button_id, modal_type: Literal["modal", "slide-over"] = "modal"):
        super().__init__(button_id)
        if modal_type == "slide-over":
            self.modal = ModalSlideOver(f"{button_id}_modal")
            self.toggle = "offcanvas"
        else:
            self.modal = Modal(f"{button_id}_modal")
            self.toggle = "modal"

    def modal_title(self, title):
        if not self.modal:
            self.modal = Modal(f"{self.button_id}_modal")
        self.modal.title(title)
        return self

    def modal_body(self, body_html):
        if not self.modal:
            self.modal = Modal(f"{self.button_id}_modal")
        self.modal.body(body_html)
        return self

    def modal_footer_actions(self, buttons):
        if not self.modal:
            self.modal = Modal(f"{self.button_id}_modal")
        self.modal.footer_buttons(buttons)
        return self

    def close_modal_by_clicking_away(self, close_modal=False):
        if not self.modal:
            self.modal = Modal(f"{self.button_id}_modal")
        self.modal.close_modal_by_clicking_away(close_modal)
        return self

    def modal_lg(self):
        if not self.modal:
            self.modal = Modal(f"{self.button_id}_modal")
        self.modal.modal_lg()
        return self

    def modal_sm(self):
        if not self.modal:
            self.modal = Modal(f"{self.button_id}_modal")
        self.modal.modal_sm()
        return self

    def modal_md(self):
        if not self.modal:
            self.modal = Modal(f"{self.button_id}_modal")
        self.modal.modal_md()
        return self

    def modal_xl(self):
        if not self.modal:
            self.modal = Modal(f"{self.button_id}_modal")
        self.modal.modal_xl()
        return self

    def modal_fullscreen(self):
        if not self.modal:
            self.modal = Modal(f"{self.button_id}_modal")
        self.modal.modal_fullscreen()
        return self

    def render(self) -> Markup | Self:
        modal_id = f"{self.button_id}_modal"
        js_action_str = f'data-bs-toggle="{self.toggle}" data-bs-target="#{modal_id}"' if not self.js_action_code else f'onclick="{self.js_action_code}"'
        extra_attrs_str = " ".join(f'{key}="{value}"' for key, value in self.extra_attrs.items())
        button_html = f'<button id="{self.button_id}" type="button" class="mb-3 {self.button_classes}" {js_action_str} {extra_attrs_str}>{self.button_label}</button>'
        self.modal = self.modal.render() if self.modal else ""
        modal_html = str(self.modal) if self.modal else ""
        return Markup(f"{button_html}\n{modal_html}")

    def __str__(self):
        return self.render()
