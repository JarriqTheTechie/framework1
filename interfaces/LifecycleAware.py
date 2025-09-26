class LifecycleAware:
    def on_request_start(self, context: dict):
        """Before the request is processed (after routing)."""
        pass

    def on_request_end(self, context: dict):
        """After response is returned or exception is raised."""
        pass

    def on_request_exception(self, context: dict):
        """When an exception occurs during request handling."""
        pass

    def on_response_sent(self, context: dict):
        """Final hook after response is sent to the client (if supported)."""
        pass