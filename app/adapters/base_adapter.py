from abc import ABC, abstractmethod

from app.models.schemas import StateSnapshot


class BaseAdapter(ABC):
    """Base interface for mocked platform snapshot adapters."""

    @abstractmethod
    def collect_snapshot(self, mode: str = "mock") -> StateSnapshot:
        raise NotImplementedError
