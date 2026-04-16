import pytest
from fastapi.testclient import TestClient

import app.api.routes as api_routes
from app.core.approval_repository import ApprovalRepository
from app.core.approval_service import ApprovalService
from app.core.baseline_service import BaselineService
from app.core.correlation_service import CorrelationService
from app.core.history_repository import HistoryRepository
from app.core.history_service import HistoryService
from app.core.runtime_observation_repository import RuntimeObservationRepository
from app.core.runtime_observation_service import RuntimeObservationService
from app.main import app

client = TestClient(app)


def build_history_service(tmp_path):
    repository = HistoryRepository(db_path=tmp_path / "history.db")
    service = HistoryService(repository=repository)
    runtime_repository = RuntimeObservationRepository(db_path=tmp_path / "history.db")
    runtime_service = RuntimeObservationService(repository=runtime_repository)
    api_routes.history_service = service
    api_routes.correlation_service = CorrelationService(repository=service.repository)
    api_routes.baseline_service = BaselineService(repository=service.repository)
    api_routes.approval_service = ApprovalService(
        repository=ApprovalRepository(db_path=tmp_path / "history.db")
    )
    api_routes.runtime_observation_repository = runtime_repository
    api_routes.runtime_observation_service = runtime_service
    macos_adapter = api_routes.state_manager.adapters.get("macos")
    if macos_adapter is not None and hasattr(macos_adapter, "runtime_observation_service"):
        macos_adapter.runtime_observation_service = runtime_service
    return service


def test_history_database_initializes(tmp_path):
    repository = HistoryRepository(db_path=tmp_path / "history.db")

    assert repository.db_path.exists()
    assert repository.get_event("missing-event") is None


def test_snapshot_persists_history_event(tmp_path):
    build_history_service(tmp_path)

    response = client.get("/snapshot?platform=linux&mode=mock")
    assert response.status_code == 200

    history_response = client.get("/history?event_type=snapshot_event")
    assert history_response.status_code == 200
    events = history_response.json()
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "snapshot_event"
    assert event["platform"] == "linux"
    assert event["mode"] == "mock"
    assert event["issue_count"] >= 0

    event_detail = client.get(f"/history/{event['event_id']}")
    assert event_detail.status_code == 200
    detail = event_detail.json()
    assert detail["payload"]["snapshot"]["system_info"]["os_name"] == "Linux"
    assert detail["health_score"] == event["health_score"]


def test_plan_persists_history_event(tmp_path):
    build_history_service(tmp_path)

    response = client.get("/plan?platform=linux&mode=mock")
    assert response.status_code == 200

    events = client.get("/history?event_type=plan_event").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "plan_event"
    assert events[0]["issue_count"] >= 0


def test_execute_persists_history_event(tmp_path):
    build_history_service(tmp_path)

    response = client.get("/execute?platform=linux&mode=mock")
    assert response.status_code == 200

    events = client.get("/history?event_type=execute_event").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "execute_event"
    assert events[0]["health_score"] >= 0


def test_history_recent_returns_timeline_items(tmp_path):
    build_history_service(tmp_path)

    client.get("/snapshot?platform=linux&mode=mock")
    client.get("/plan?platform=linux&mode=mock")
    client.get("/execute?platform=linux&mode=mock")

    recent = client.get("/history/recent?limit=3").json()
    assert isinstance(recent, list)
    assert len(recent) == 3
    assert recent[0]["event_type"] in {"snapshot_event", "plan_event", "execute_event"}


def test_history_filtering_by_platform_and_mode(tmp_path):
    build_history_service(tmp_path)

    client.get("/snapshot?platform=linux&mode=mock")
    client.get("/snapshot?platform=windows&mode=mock")

    linux_events = client.get("/history?platform=linux&mode=mock").json()
    windows_events = client.get("/history?platform=windows&mode=mock").json()

    assert all(event["platform"] == "linux" for event in linux_events)
    assert all(event["platform"] == "windows" for event in windows_events)
