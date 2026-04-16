from __future__ import annotations

from typing import Any

from app.core.history_repository import HistoryRepository
from app.models.schemas import ExecuteResponse, PlanResponse, StateSnapshot


class HistoryService:
    def __init__(self, repository: HistoryRepository | None = None) -> None:
        self.repository = repository or HistoryRepository()

    def _normalize_payload(self, payload: dict) -> dict:
        return payload

    def record_snapshot_event(self, snapshot: StateSnapshot, platform: str, mode: str) -> str:
        payload = {
            "snapshot": snapshot.model_dump(),
        }
        return self.repository.record_event(
            event_type="snapshot_event",
            platform=platform,
            mode=mode,
            health_score=snapshot.health_score,
            risk_score=snapshot.risk_score,
            issue_count=len(snapshot.issues),
            payload=self._normalize_payload(payload),
        )

    def record_plan_event(self, plan_response: PlanResponse, platform: str, mode: str) -> str:
        payload = plan_response.model_dump()
        return self.repository.record_event(
            event_type="plan_event",
            platform=platform,
            mode=mode,
            health_score=plan_response.snapshot.health_score,
            risk_score=plan_response.snapshot.risk_score,
            issue_count=len(plan_response.snapshot.issues),
            payload=self._normalize_payload(payload),
        )

    def record_execute_event(self, execute_response: ExecuteResponse, platform: str, mode: str) -> str:
        payload = execute_response.model_dump()
        return self.repository.record_event(
            event_type="execute_event",
            platform=platform,
            mode=mode,
            health_score=execute_response.snapshot.health_score,
            risk_score=execute_response.snapshot.risk_score,
            issue_count=len(execute_response.snapshot.issues),
            payload=self._normalize_payload(payload),
        )

    def get_event(self, event_id: str) -> dict | None:
        return self.repository.get_event(event_id)

    def list_events(
        self,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
        platform: str | None = None,
        mode: str | None = None,
    ) -> list[dict]:
        return self.repository.list_events(limit=limit, offset=offset, event_type=event_type, platform=platform, mode=mode)

    def recent_events(
        self,
        limit: int = 10,
        platform: str | None = None,
        mode: str | None = None,
        event_type: str | None = None,
    ) -> list[dict]:
        return self.repository.recent_events(limit=limit, platform=platform, mode=mode, event_type=event_type)
