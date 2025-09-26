from ._ContainerInterface import ContainerInterface


class ServiceContainer(ContainerInterface):
    def __init__(self):
        self._services = {}
        self._singletons = {}
        self._instances = {}

    def add(self, id, service, singleton=False):
        """Add a service or singleton to the container."""
        if singleton:
            self._singletons[id] = service
        else:
            self._services[id] = service

    def get(self, id):
        """Retrieve a service or singleton from the container."""
        if self.has_singleton(id):
            if id not in self._instances:
                self._instances[id] = self._singletons[id]()
            return self._instances[id]

        if self.has(id):
            try:
                return self._services[id]()
            except TypeError:
                return self._services[id]

        pass

    def has(self, id) -> bool:
        """Check if the service exists in the container."""
        return id in self._services

    def has_singleton(self, id) -> bool:
        """Check if the singleton exists in the container."""
        return id in self._singletons
