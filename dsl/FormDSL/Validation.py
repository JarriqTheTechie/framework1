from typing import Callable, Optional
import inspect

class ValidationRule:
    def __init__(self, func, error_message: str):
        self.func = func
        self.error_message = error_message

    def validate(self, value, context=None):
        sig = inspect.signature(self.func)
        try:
            # Supports func(value) or func(value, context)
            if len(sig.parameters) == 2:
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
