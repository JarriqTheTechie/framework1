from framework1.core_services.Request import Request
from framework1.database.QueryBuilder import QueryBuilder
from markupsafe import escape
from typing import Self, Callable


class Filter:
    def __init__(self, name: str):
        self._key = name
        self._label = name.replace("_", " ").title()
        self._query_callback = None
        self._toggle = False

    @classmethod
    def make(cls, name: str) -> Self:
        return cls(name)

    def label(self, label: str) -> Self:
        self._label = label
        return self

    def toggle(self, toogle: bool=True):
        self._toggle = toogle
        return self


    def query(self, callback: Callable[[QueryBuilder], QueryBuilder]) -> Self:
        self._query_callback = callback
        return self

    def apply(self, query: QueryBuilder, persist_filters: bool = False) -> QueryBuilder:
        request = Request()
        session = request.session()
        session_key = f"{self._key}_filter"

        value = request.input(f"filter_{self._key}")

        if persist_filters:
            if value is not None:
                if value == "":
                    session.pop(session_key, None)
                else:
                    session[session_key] = value
            else:
                value = session.get(session_key)

        # ✅ Apply if explicitly set or defaulted
        if value or (value is None and getattr(self, "_default_checked", False)):
            if self._query_callback:
                return self._query_callback(query)

        return query

    def default_checked(self, default: bool = False):
        self._default_checked = default
        return self

    def group(self, key: str):
        self._group_key = key
        return self

    def render_input(self, persist_filters: bool = False) -> str:
        request = Request()
        session = request.session()
        session_key = f"{self._key}_filter"

        # Determine if this filter should be checked
        value = request.input(f"filter_{self._key}")
        checked = False

        if persist_filters:
            if value is not None:
                checked = True
            elif session.get(session_key):
                checked = True
        else:
            checked = bool(value)

        # Fallback to default if still unchecked
        if not checked and getattr(self, "_default_checked", False):
            checked = True

        toggle_class = "form-check form-switch" if self._toggle else "form-check"
        toggle_role = "switch" if self._toggle else ""

        return f'''
        <div class="{toggle_class}">
          <input class="form-check-input" type="checkbox" role="{toggle_role}"
                 name="filter_{self._key}" id="filter_{self._key}" {'checked' if checked else ''}>
          <label class="form-check-label fw-bold" for="filter_{self._key}">
            {escape(self._label)}
          </label>
        </div>
        '''
