from abc import ABC, abstractmethod
from typing import List

from app.models.schemas import Issue, StateSnapshot


class BaseDetector(ABC):
    """Base interface for snapshot issue detection."""

    @abstractmethod
    def detect(self, snapshot: StateSnapshot) -> List[Issue]:
        raise NotImplementedError
