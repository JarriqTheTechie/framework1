import inspect
from framework1.service_container._Injector import singleton


@singleton
class ViewProps:
    @classmethod
    def compact(cls) -> dict:
        # Grab caller frame locals, but DO NOT mutate them
        frame = inspect.currentframe()
        try:
            caller_locals = frame.f_back.f_locals  # may be FrameLocalsProxy
            props = dict(caller_locals)            # materialize real dict
        finally:
            del frame  # avoid reference cycles

        # filter out "__*" and remove view_props safely
        filtered = {k: v for k, v in props.items() if not k.startswith("__")}
        filtered.pop("view_props", None)

        # If you ever re-enable the DSL injection, do it on the dict you own
        """
        html_component_dsl = {
            "Heading": Heading,
            "Subheading": Subheading,
            "Button": Button,
            "ModalButton": ModalButton,
            "Table": Table,
            "Dropdown": Dropdown,
        }
        filtered.update(html_component_dsl)
        """

        return filtered

    @classmethod
    def api_compact(cls, exclude_keys: list[str] = None, include_keys: list[str] = None) -> dict:
        exclude_keys = exclude_keys or []
        include_keys = include_keys or []

        frame = inspect.currentframe()
        try:
            caller_locals = frame.f_back.f_locals
            props = dict(caller_locals)
        finally:
            del frame

        def allowed(k: str) -> bool:
            if k.startswith("__"):
                return False
            if k == "view_props":
                return False
            if k in exclude_keys:
                return False
            if include_keys and k not in include_keys:
                return False
            return True

        return {k: v for k, v in props.items() if allowed(k)}
