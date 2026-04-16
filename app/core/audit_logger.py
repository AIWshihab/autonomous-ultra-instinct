from datetime import datetime
from typing import List


class AuditLogger:
    """Log audit events for system operations."""

    def __init__(self) -> None:
        self.events: List[str] = []

    def record(self, event: str) -> None:
        timestamp = datetime.utcnow().isoformat() + "Z"
        self.events.append(f"{timestamp} {event}")

    def get_events(self) -> List[str]:
        return list(self.events)
