from typing import Any, Optional

class StimulusMixin:
    """
    Provides declarative StimulusJS bindings for Framework1 DSL components (Form, Field, InfoList, etc.)
    and routes all data-attribute manipulation through Form.set_data_attribute().
    """

    def controller(self, name: str):
        """Attach a Stimulus controller to this component."""
        if not hasattr(self, "set_data_attribute"):
            raise AttributeError(f"{self.__class__.__name__} must define set_data_attribute().")

        # Stimulus controller identifier
        self._stimulus_controller = name
        self.set_data_attribute("data-controller", name)
        return self

    def action(self, event: str, method: str):
        """
        Add an event binding for the Stimulus controller.

        Example:
            .action("change", "updateScore")
            -> data-action="change->risk-calculator#updateScore"
        """
        controller = getattr(self, "_stimulus_controller", None)
        if not controller:
            raise ValueError("Stimulus controller not set. Call .controller('name') first.")

        existing = getattr(self, "data_attributes", {}).get("data-action", "")
        new_action = f"{event}->{controller}#{method}"

        # Avoid duplicates and combine multiple actions
        actions = existing.split()
        if new_action not in actions:
            actions.append(new_action)

        self.set_data_attribute("data-action", " ".join(actions).strip())
        return self

    def target(self, name: str, for_field: Optional[str] = None):
        """
        Mark a sub-element or field as a Stimulus target.

        Example:
            .target("score") -> data-risk-calculator-target="score"
        """
        controller = getattr(self, "_stimulus_controller", None)
        if not controller:
            raise ValueError("Stimulus controller not set. Call .controller('name') first.")

        self.set_data_attribute(f"data-{controller}-target", name)

        if for_field:
            self.field_name = for_field
        return self

    def data(self, key: str, value: Any):
        """
        Attach arbitrary data attributes for Stimulus values or params.

        Example:
            .data("risk-calculator-client-id-value", 1021)
            -> data-risk-calculator-client-id-value="1021"
        """
        if not hasattr(self, "set_data_attribute"):
            raise AttributeError(f"{self.__class__.__name__} must define set_data_attribute().")

        self.set_data_attribute(f"data-{key}", str(value))
        return self

    def value(self, name: str, value: Any):
        """
        Shortcut for Stimulus Values API.

        Example:
            .value("client-id", 1021)
            -> data-risk-calculator-client-id-value="1021"
        """
        controller = getattr(self, "_stimulus_controller", None)
        if not controller:
            raise ValueError("Stimulus controller not set. Call .controller('name') first.")
        key = f"{controller}-{name}-value"
        return self.data(key, value)
