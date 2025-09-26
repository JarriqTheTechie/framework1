from abc import ABC, abstractmethod

class ContainerInterface(ABC):
    @abstractmethod
    def get(self, id):
        """Find and return the entry for the given id."""
        pass

    @abstractmethod
    def has(self, id) -> bool:
        """Return True if the container contains an entry for the given id."""
        pass