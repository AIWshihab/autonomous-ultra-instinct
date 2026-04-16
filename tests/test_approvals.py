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


def setup_services(tmp_path):
    repository = HistoryRepository(db_path=tmp_path / "history.db")
    history_service = HistoryService(repository=repository)
    runtime_repository = RuntimeObservationRepository(db_path=tmp_path / "history.db")
    runtime_service = RuntimeObservationService(repository=runtime_repository)
    api_routes.history_service = history_service
    api_routes.correlation_service = CorrelationService(repository=repository)
    api_routes.baseline_service = BaselineService(repository=repository)
    api_routes.approval_service = ApprovalService(
        repository=ApprovalRepository(db_path=tmp_path / "history.db")
    )
    api_routes.runtime_observation_repository = runtime_repository
    api_routes.runtime_observation_service = runtime_service
    macos_adapter = api_routes.state_manager.adapters.get("macos")
    if macos_adapter is not None and hasattr(macos_adapter, "runtime_observation_service"):
        macos_adapter.runtime_observation_service = runtime_service


def test_approval_request_creation_from_approval_gated_steps(tmp_path):
    setup_services(tmp_path)

    plan_response = client.get("/plan?platform=windows&mode=live")
    assert plan_response.status_code == 200

    approvals_response = client.get("/approvals?status=pending&platform=windows&mode=live")
    assert approvals_response.status_code == 200
    approvals = approvals_response.json()
    assert approvals
    assert all(item["request"]["status"] == "pending" for item in approvals)
    assert all(item["request"]["request_id"] for item in approvals)


def test_pending_approval_queue_retrieval(tmp_path):
    setup_services(tmp_path)
    client.get("/plan?platform=windows&mode=live")

    response = client.get("/approvals?status=pending&platform=windows&mode=live")
    assert response.status_code == 200
    queue = response.json()
    assert isinstance(queue, list)
    assert queue
    assert "request" in queue[0]
    assert "incident_key" in queue[0]["request"]
    assert "action_type" in queue[0]["request"]


def test_approve_path_updates_status_and_records_decision(tmp_path):
    setup_services(tmp_path)
    client.get("/plan?platform=windows&mode=live")

    queue = client.get("/approvals?status=pending&platform=windows&mode=live").json()
    request_id = queue[0]["request"]["request_id"]

    decision_response = client.post(
        f"/approvals/{request_id}/approve",
        json={"decision_reason": "Approved for controlled remediation simulation."},
    )
    assert decision_response.status_code == 200
    decision = decision_response.json()
    assert decision["operator_action"] == "approve"
    assert decision["resulting_status"] == "approved"

    detail_response = client.get(f"/approvals/{request_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["request"]["status"] == "approved"
    assert detail["decisions"]


def test_deny_path_updates_status_and_records_decision(tmp_path):
    setup_services(tmp_path)
    client.get("/plan?platform=windows&mode=live")

    queue = client.get("/approvals?status=pending&platform=windows&mode=live").json()
    request_id = queue[0]["request"]["request_id"]

    decision_response = client.post(
        f"/approvals/{request_id}/deny",
        json={"decision_reason": "Denied pending additional review."},
    )
    assert decision_response.status_code == 200
    decision = decision_response.json()
    assert decision["operator_action"] == "deny"
    assert decision["resulting_status"] == "denied"

    detail_response = client.get(f"/approvals/{request_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["request"]["status"] == "denied"


def test_recent_decisions_retrieval(tmp_path):
    setup_services(tmp_path)
    client.get("/plan?platform=windows&mode=live")
    queue = client.get("/approvals?status=pending&platform=windows&mode=live").json()
    request_id = queue[0]["request"]["request_id"]
    client.post(
        f"/approvals/{request_id}/approve",
        json={"decision_reason": "Approved after triage."},
    )

    response = client.get("/approvals/recent?limit=5")
    assert response.status_code == 200
    decisions = response.json()
    assert decisions
    assert decisions[0]["request_id"] == request_id


def test_invalid_approval_transition_rejected(tmp_path):
    setup_services(tmp_path)
    client.get("/plan?platform=windows&mode=live")
    queue = client.get("/approvals?status=pending&platform=windows&mode=live").json()
    request_id = queue[0]["request"]["request_id"]

    approve_response = client.post(
        f"/approvals/{request_id}/approve",
        json={"decision_reason": "Approved once."},
    )
    assert approve_response.status_code == 200

    second_approve = client.post(
        f"/approvals/{request_id}/approve",
        json={"decision_reason": "Trying to approve twice."},
    )
    assert second_approve.status_code == 400
    assert "Invalid approval transition" in second_approve.json()["detail"]


def test_execute_halts_when_approval_pending(tmp_path):
    setup_services(tmp_path)
    client.get("/plan?platform=windows&mode=live")

    execute_response = client.get("/execute?platform=windows&mode=live")
    assert execute_response.status_code == 200
    payload = execute_response.json()
    assert payload["execution_halted_by_approval"] is True
    assert payload["approval_halt_reasons"]
    executed_types = {item["action_type"] for item in payload["dispatch"]["executed_actions"]}
    assert "restart_service" not in executed_types


def test_state_updates_after_approval_and_denial(tmp_path):
    setup_services(tmp_path)
    client.get("/plan?platform=windows&mode=live")
    queue = client.get("/approvals?status=pending&platform=windows&mode=live").json()
    assert len(queue) >= 2

    approved_request_id = queue[0]["request"]["request_id"]
    denied_request_id = queue[1]["request"]["request_id"]
    client.post(
        f"/approvals/{approved_request_id}/approve",
        json={"decision_reason": "Approved service remediation action."},
    )
    client.post(
        f"/approvals/{denied_request_id}/deny",
        json={"decision_reason": "Denied this action due to risk concerns."},
    )

    execute_response = client.get("/execute?platform=windows&mode=live")
    assert execute_response.status_code == 200
    payload = execute_response.json()
    states = {state["current_state"] for state in payload["incident_states"]}
    assert "denied" in states or "blocked" in states
    assert payload["execution_halted_by_approval"] is True


def test_approval_payload_shape_and_persistence(tmp_path):
    setup_services(tmp_path)
    client.get("/plan?platform=windows&mode=live")
    queue = client.get("/approvals?status=pending&platform=windows&mode=live").json()
    request = queue[0]["request"]
    request_id = request["request_id"]

    expected_keys = {
        "request_id",
        "incident_key",
        "playbook_id",
        "step_id",
        "action_id",
        "action_type",
        "platform",
        "mode",
        "risk_tier",
        "action_confidence",
        "policy_reason",
        "justification_summary",
        "current_incident_state",
        "current_step_state",
        "created_at",
        "status",
    }
    assert expected_keys.issubset(set(request.keys()))

    client.post(
        f"/approvals/{request_id}/approve",
        json={"decision_reason": "Approved for persistence check."},
    )
    detail = client.get(f"/approvals/{request_id}").json()
    assert detail["request"]["status"] == "approved"
    assert detail["decisions"]
