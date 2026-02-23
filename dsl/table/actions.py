from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional, Union
from markupsafe import escape
from flask import url_for


ParamValue = Union[str, int, float, bool]
ParamResolver = Callable[[Mapping[str, Any]], ParamValue]


class TableAction:
    """
    Minimal row action helper (non-reactive).

    Usage:
        TableAction("Edit", url=lambda r: f"/clients/{r['id']}/edit", icon="ri-pencil-line")
        TableAction("Edit", endpoint="clients.edit", params={"client_id": lambda r: r["id"]})
    """

    def __init__(
        self,
        label: str,
        url: Optional[str | Callable[[Mapping[str, Any]], str]] = None,
        *,
        endpoint: Optional[str] = None,
        params: Optional[Dict[str, ParamValue | ParamResolver]] = None,
        method: str = "GET",
        icon: Optional[str] = None,
        style: str = "secondary",
        confirm: Optional[str] = None,
        visible: Optional[Callable[[Mapping[str, Any]], bool]] = None,
        new_tab: bool = False,
        scope: str = "row",  # row | header | bulk
    ):
        self.label: str = label
        self.url: str | Callable[[Mapping[str, Any]], str] | None = url or None
        self.endpoint: Optional[str] = endpoint
        self.params: Dict[str, ParamValue | ParamResolver] = params or {}
        self.method: str = method.upper()
        self.icon: Optional[str] = icon
        self.style: str = style
        self.confirm: Optional[str] = confirm
        self.visible: Optional[Callable[[Mapping[str, Any]], bool]] = visible
        self.new_tab: bool = new_tab
        self.scope: str = scope

    def _resolve_params(self, record: Mapping[str, Any]) -> Dict[str, ParamValue]:
        resolved: Dict[str, ParamValue] = {}
        for key, val in self.params.items():
            if callable(val):
                try:
                    resolved[key] = val(record)  # type: ignore[assignment]
                except Exception:
                    continue
            else:
                resolved[key] = val
        return resolved

    def _resolve_url(self, record: Mapping[str, Any]) -> str:
        # Prefer endpoint if provided
        if self.endpoint:
            try:
                return url_for(self.endpoint, **self._resolve_params(record))
            except Exception:
                pass

        if callable(self.url):
            return self.url(record)
        if self.url and isinstance(record, Mapping):
            try:
                return self.url.format(**record)  # type: ignore[union-attr]
            except Exception:
                return str(self.url)
        return str(self.url or "#")

    def should_render(self, record: Mapping[str, Any]) -> bool:
        if self.visible is None:
            return True
        try:
            return bool(self.visible(record))
        except Exception:
            return False

    def render(self, record: Mapping[str, Any], record_id: str | int | None = None) -> str:
        """Return HTML for a single action button."""
        if not self.should_render(record):
            return ""

        url = escape(self._resolve_url(record))
        label = escape(self.label)
        icon_html = f'<i class="{escape(self.icon)} me-1"></i>' if self.icon else ""
        target = ' target="_blank" rel="noopener noreferrer"' if self.new_tab else ""
        confirm = ""
        if self.confirm:
            confirm = f"return confirm('{escape(self.confirm)}');"

        if self.method == "GET":
            onclick = f' onclick="{confirm}"' if confirm else ""
            return (
                f'<a class="btn btn-sm btn-{escape(self.style)}" href="{url}" {target}{onclick}>'
                f"{icon_html}{label}</a>"
            )

        # Fallback: simple form POST for non-GET
        onclick = f' onclick="{confirm}"' if confirm else ""
        return (
            f'<form method="post" action="{url}" class="d-inline">'
            f'<input type="hidden" name="_method" value="{escape(self.method)}">'
            + (f'<input type="hidden" name="id" value="{escape(record_id)}">' if record_id else "")
            + (
                f'<button type="submit" class="btn btn-sm btn-{escape(self.style)}"{onclick}>'
                f"{icon_html}{label}</button></form>"
            )
        )
