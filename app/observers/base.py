from abc import ABC, abstractmethod
from app.models.schemas import StateSnapshot


class ObserverBase(ABC):
    """Base interface for state observers."""

    @abstractmethod
    def observe(self) -> StateSnapshot:
        raise NotImplementedError
