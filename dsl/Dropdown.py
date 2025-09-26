from typing import Self

from markupsafe import Markup


class Action:
    def __init__(self, action_id):
        self.__href = "#"
        self.__action_id = action_id
        self.__label_text = ""
        self.__js_onclick_function = ""
        self.__is_spa_navigation = False
        self.__target_id = ""

    def label(self, text):
        self.__label_text = text
        return self

    def link(self, href):
        self.__href = href
        return self

    def js_action(self, func):
        self.__js_onclick_function = func
        return self

    def spa_navigate(self, is_spa_navigation: bool = True):
        self.__is_spa_navigation = is_spa_navigation
        return self

    def target(self, target_id):
        self.__target_id = target_id
        return self

    def render(self):
        # This method can be customized for more complex action handling
        return Markup(f"""
        <a class="dropdown-item" 
            href="{self.__href}" 
            onclick="{self.__js_onclick_function}" 
            {'hx-boost="true"' if self.__is_spa_navigation else ""}
            >
            {self.__label_text}
        </a>
        """)

    def __str__(self):
        return self.render()


class Dropdown:
    def __init__(self, trigger_id):
        self.trigger_id = trigger_id
        self.button_class = "bg-transparent dropdown-toggle border-0 shadow-none no-after-content"
        self.button_content = ""
        self.container_class = ""
        self.menu_items = []

    def label(self, content):
        self.button_content = content
        return self

    def btn_classes(self, class_name):
        self.button_class = self.button_class + class_name
        return self

    def container_classes(self, class_name):
        self.container_class = class_name
        return self

    def icon(self, icon_src):
        self.button_content = f'<img src="{icon_src}" alt="" height="24px"> {self.button_content}'
        return self

    def actions(self, actions):
        for action in actions:
            self.menu_items.append(action.render())
        return self

    def render(self) -> Markup | Self:
        items_html = "\n            ".join(self.menu_items)
        return Markup(f"""
<div class="dropdown">
    <button class="{self.button_class}" type="button" id="{self.trigger_id}"
            data-bs-toggle="dropdown"
            aria-haspopup="true"
            aria-expanded="false">
        {self.button_content}
    </button>
    <div class="dropdown-menu {self.container_class}" aria-labelledby="{self.trigger_id}">
        {items_html}
    </div>
</div>
""")

    def __str__(self):
        return self.render()
