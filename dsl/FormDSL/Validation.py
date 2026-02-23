from typing import Callable, Optional
import inspect

class ValidationRule:
    def __init__(self, func, error_message: str):
        self.func = func
        self.error_message = error_message
        try:
            self._arity = len(inspect.signature(func).parameters)
        except Exception:
            self._arity = 1

    def validate(self, value, context=None):
        try:
            # Supports func(value) or func(value, context)
            if self._arity == 2:
                valid = self.func(value, context)
            else:
                valid = self.func(value)
        except Exception as e:
            # If validation function throws, treat as failure
            return f"{self.error_message} ({e})"

        # Return error message if False or string
        if valid is False:
            return self.error_message
        if isinstance(valid, str):
            return valid
        return None
