import logging
from contextlib import contextmanager
from datetime import datetime

class ErrorHandler:
    def __init__(self, name="ErrorHandler", log_to_console=True, log_to_file=None, log_level=logging.DEBUG):
        """
        :param name: logger name
        :param log_to_console: whether to log to the terminal
        :param log_to_file: filepath string to enable file logging
        :param log_level: default log level (e.g., logging.DEBUG)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level)

        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        if log_to_console and not self._has_handler(logging.StreamHandler):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        if log_to_file and not self._has_handler(logging.FileHandler, log_to_file):
            file_handler = logging.FileHandler(log_to_file)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def _has_handler(self, handler_type, filename=None):
        for handler in self.logger.handlers:
            if isinstance(handler, handler_type):
                if isinstance(handler, logging.FileHandler):
                    return handler.baseFilename == filename
                return True
        return False

    @contextmanager
    def handle_errors(self, exception_map, fallback=None, log_level=logging.ERROR):
        try:
            yield
        except tuple(exception_map.keys()) as e:
            message = exception_map.get(type(e), "An error occurred.")
            self.logger.log(log_level, f"{message} | Exception: {type(e).__name__}: {e}")
            if fallback:
                fallback(message, e)
