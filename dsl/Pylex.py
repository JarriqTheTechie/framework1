from typing import Self, Literal, TypeVar
import re

SELF_CLOSING_TAGS: Literal[
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr"
]

HTML_TAGS: Literal[
    "a",
    "abbr",
    "address",
    "article",
    "aside",
    "audio",
    "b",
    "bdi",
    "bdo",
    "blockquote",
    "body",
    "button",
    "canvas",
    "caption",
    "cite",
    "code",
    "colgroup",
    "data",
    "datalist",
    "dd",
    "del",
    "details",
    "dfn",
    "dialog",
    "div",
    "dl",
    "dt",
    "em",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "hgroup",
    "html",
    "i",
    "iframe",
    "ins",
    "kbd",
    "label",
    "legend",
    "li",
    "main",
    "map",
    "mark",
    "meter",
    "nav",
    "noscript",
    "object",
    "ol",
    "optgroup",
    "option",
    "output",
    "p",
    "picture",
    "pre",
    "progress",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "script",
    "section",
    "select",
    "small",
    "span",
    "strong",
    "style",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "template",
    "textarea",
    "tfoot",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "u",
    "ul",
    "var",
    "video"
]

T = TypeVar('T', str, 'Component', int, 'LiteralString', list[str], list['Component'], list['LiteralString'])


class Component:
    def __init__(self, children: T | list[T] | str = "", *args, **kwargs):
        self.__tag = self.__class__.__name__.lower()
        if self.__tag == "component":
            self.__tag = "div"
        self.__buffer = []
        self.__attributes = ""
        self.__self_closing_tags: list[SELF_CLOSING_TAGS] = [
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "source",
            "track",
            "wbr"
        ]
        self.__self_closing = False

        for attribute, value in kwargs.items():
            self.__attributes += self.__explode_attributes(attribute, value)

        if not isinstance(children, (list,)):
            children = [str(children)]

        if children:
            for item in children:
                # if item == "None":
                #     item = ""
                try:
                    self.__add(item.__render())
                except AttributeError:
                    self.__add(item)

    def __add(self, children: str | Self):
        self.__buffer.append(children)
        return self

    def __convert_underscores_to_dashes(self, string: str) -> str:
        return re.sub(r"_", "-", string)

    def __explode_attributes(self, attribute, value):
        attributes_string = " "
        if attribute != "style" and attribute not in ["tag_", "type_"]:
            if attribute == "class_":
                attribute = "class"
            attributes_string += "".join([f'{self.__convert_underscores_to_dashes(attribute)}="{value}"'])
            return attributes_string

        if attribute == "style":
            attributes_string += f'style="{value}"'
            return attributes_string

        if attribute == "tag_":
            self.__tag = value
            return ""

        if attribute == "type_":
            attribute = "type"
            attributes_string += "".join([f'{attribute}="{value}"'])
            return attributes_string

    def __render(self):
        if self.__tag in self.__self_closing_tags:
            return self.__render_self_closing()
        html = f"<{self.__tag}{self.__attributes}>".rstrip() + " ".join(self.__buffer) + f"</{self.__tag}>"
        return html

    def __render_self_closing(self):
        html = f"<{self.__tag}{self.__attributes} />"
        return html

    def __str__(self):
        return self.__render()

    def flush(self):
        return self.__render()


def template(children: T | list[T] | str = "", *args, **kwargs):
    return Component(tag_="template", children=children, *args, **kwargs)


def html(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='html', children=children, *args, **kwargs)


def head(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='head', children=children, *args, **kwargs)


def meta(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='meta', children=children, *args, **kwargs)


def title(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='title', children=children, *args, **kwargs)


def style(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='style', children=children, *args, **kwargs)


def body(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='body', children=children, *args, **kwargs)


def link(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='link', children=children, *args, **kwargs)


def script(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='script', children=children, *args, **kwargs)


def div(children: T | list[T] | str = "", *args, **kwargs):
    return Component(children=children, *args, **kwargs)


def img(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='img', children=children, *args, **kwargs)


def p(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='p', children=children, *args, **kwargs)


def h1(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='h1', children=children, *args, **kwargs)


def h2(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='h2', children=children, *args, **kwargs)


def h3(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='h3', children=children, *args, **kwargs)


def h4(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='h4', children=children, *args, **kwargs)


def h5(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='h5', children=children, *args, **kwargs)


def h6(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='h6', children=children, *args, **kwargs)


def a(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='a', children=children, *args, **kwargs)


def button(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='button', children=children, *args, **kwargs)


def br(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='br', children=children, *args, **kwargs)


def hr(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='hr', children=children, *args, **kwargs)


def span(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='span', children=children, *args, **kwargs)


def nav(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='nav', children=children, *args, **kwargs)


def i(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='i', children=children, *args, **kwargs)


def ul(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='ul', children=children, *args, **kwargs)


def li(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='li', children=children, *args, **kwargs)


def form(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='form', children=children, *args, **kwargs)

def input(children: T | list[T] | str = "", *args, **kwargs):
    return div(tag_='input', children=children, *args, **kwargs)

# print(html(children=[
#     body([
#         div(id="app", children=[
#             template(shadowrootmode="open", children=[
#                 style(children=":host { background: dimgrey; }"),
#                 span("Hello World")
#             ])
#         ])
#     ])
# ]))
