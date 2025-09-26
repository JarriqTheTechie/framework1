import inspect

from framework1.service_container._Injector import singleton


@singleton
class ViewProps:
    @classmethod
    def compact(self) -> dict:
        props = inspect.stack()[1][0].f_locals
        # remove all keys that begin with a double underscore
        for key in list(props.keys()):
            if key.startswith("__"):
                del props[key]


        del props['view_props']

        """
        html_component_dsl = {
            "Heading": Heading,
            "Subheading": Subheading,
            "Button": Button,
            "ModalButton": ModalButton,
            "Table": Table,
            "Dropdown": Dropdown, }
        props.update(html_component_dsl)
        """

        return props

    @classmethod
    def api_compact(cls, exclude_keys: list[str] = None, include_keys: list[str] = None) -> dict:
        if exclude_keys is None:
            exclude_keys = []

        if include_keys is None:
            include_keys = []


        props = inspect.stack()[1][0].f_locals
        # Filter out keys that start with double underscores, 'view_props', and any in exclude_keys
        if include_keys:
            filtered_props = {
                key: value for key, value in props.items()
                if not key.startswith("__") and key != 'view_props' and key not in exclude_keys and key in include_keys
            }
        else:
            filtered_props = {
                key: value for key, value in props.items()
                if not key.startswith("__") and key != 'view_props' and key not in exclude_keys
            }

        return filtered_props

