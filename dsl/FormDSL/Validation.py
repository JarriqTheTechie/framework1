from typing import Callable, Optional


class ValidationRule:
    def __init__(self, validation_func: Callable, error_message: str):
        self.validation_func = validation_func
        self.error_message = error_message

    def validate(self, value) -> Optional[str]:
        """Validate the value. Return error message if validation fails, otherwise None."""
        if not self.validation_func(value):
            return self.error_message
        return None
