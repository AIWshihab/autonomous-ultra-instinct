from datetime import datetime, timezone

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
from app.models.schemas import (
    CommandResult,
    ObservationBatch,
    RuntimeObservationTrace,
    ExecuteResponse,
    PlanResponse,
    ProcessInfo,
    ResourceUsage,
    StateSnapshot,
    SystemInfo,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_services(tmp_path):
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
    yield


def build_mock_live_macos_snapshot() -> StateSnapshot:
    return StateSnapshot(
        system_info=SystemInfo(
            hostname="live-macos-host",
            os_name="macOS",
            os_version="macOS 14.5",
            uptime_seconds=32100,
        ),
        resources=ResourceUsage(
            cpu_percent=11.2,
            memory_total_mb=16384,
            memory_used_mb=8192,
            disk_total_gb=512.0,
            disk_used_gb=470.0,
            disk_usage_percent=91.8,
        ),
        processes=[
            ProcessInfo(pid=101, name="Finder", cpu_percent=1.2, memory_mb=100.0, status="running"),
            ProcessInfo(pid=202, name="unsigned-sync-agent", cpu_percent=22.5, memory_mb=210.0, status="running"),
        ],
        services=[],
        open_ports=[5000],
        recent_logs=["live test snapshot"],
    )

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "autonomous-repair-agent"}


def test_snapshot_endpoint_returns_state_snapshot():
    response = client.get("/snapshot")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())
    assert snapshot.system_info.hostname == "linux-node-01"
    assert snapshot.system_info.os_name == "Linux"
    assert snapshot.resources.cpu_percent >= 0.0
    assert len(snapshot.processes) >= 2
    assert len(snapshot.services) >= 3
    assert any(service.status == "unhealthy" for service in snapshot.services)
    assert len(snapshot.issues) >= 2
    assert 0 <= snapshot.health_score <= 100
    assert 0 <= snapshot.risk_score <= 100
    assert snapshot.issue_summary.total_count == len(snapshot.issues)
    assert all(0.0 <= issue.confidence <= 1.0 for issue in snapshot.issues)
    assert all(0 <= issue.priority_score <= 100 for issue in snapshot.issues)
    assert all(issue.evidence for issue in snapshot.issues)
    assert all(issue.detection_reason for issue in snapshot.issues)
    assert all(issue.severity_reason for issue in snapshot.issues)
    assert all(issue.confidence_reason for issue in snapshot.issues)


def test_default_snapshot_uses_linux():
    response = client.get("/snapshot")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())

    assert snapshot.system_info.os_name == "Linux"
    assert "Ubuntu" in snapshot.system_info.os_version


def test_snapshot_windows_returns_windows_system_info():
    response = client.get("/snapshot?platform=windows")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())

    assert snapshot.system_info.os_name == "Windows"
    assert "Windows 11" in snapshot.system_info.os_version


def test_snapshot_macos_returns_macos_system_info():
    response = client.get("/snapshot?platform=macos")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())

    assert snapshot.system_info.os_name == "macOS"
    assert "Sonoma" in snapshot.system_info.os_version


def test_snapshot_windows_live_mode_falls_back_to_mock():
    response = client.get("/snapshot?platform=windows&mode=live")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())

    assert snapshot.system_info.os_name == "Windows"
    assert "Windows 11" in snapshot.system_info.os_version


def test_snapshot_macos_live_mode_returns_valid_state_snapshot(monkeypatch: pytest.MonkeyPatch):
    live_snapshot = build_mock_live_macos_snapshot()
    monkeypatch.setattr(
        api_routes.state_manager.adapters["macos"],
        "_collect_live_snapshot",
        lambda: live_snapshot,
    )

    response = client.get("/snapshot?platform=macos&mode=live")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())
    assert snapshot.system_info.hostname == "live-macos-host"
    assert snapshot.system_info.os_name == "macOS"
    assert snapshot.resources.disk_usage_percent == 91.8
    assert len(snapshot.processes) == 2
    assert snapshot.risk_score > 0
    assert snapshot.issue_summary.total_count == len(snapshot.issues)


def test_snapshot_includes_scores_and_issue_summary():
    response = client.get("/snapshot?platform=windows")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())

    assert snapshot.health_score < 100
    assert snapshot.risk_score > 0
    assert snapshot.issue_summary.total_count == len(snapshot.issues)
    assert snapshot.issue_summary.high_count >= 1
    assert snapshot.issues == sorted(
        snapshot.issues,
        key=lambda issue: (-issue.priority_score, issue.id),
    )


@pytest.mark.parametrize(
    ("platform", "expected_os_name"),
    [
        ("linux", "Linux"),
        ("windows", "Windows"),
        ("macos", "macOS"),
    ],
)
def test_plan_works_for_each_platform(platform: str, expected_os_name: str):
    response = client.get(f"/plan?platform={platform}")
    assert response.status_code == 200

    plan = PlanResponse.model_validate(response.json())

    assert plan.snapshot.system_info.os_name == expected_os_name
    assert len(plan.allowed_actions) >= 1
    assert all(action.policy_reason for action in plan.candidate_actions)
    assert all(action.risk_tier for action in plan.candidate_actions)
    assert all(action.execution_mode for action in plan.candidate_actions)
    assert all(action.allowed is True for action in plan.allowed_actions)
    assert plan.remediation_strategies
    assert plan.incident_states


def test_plan_includes_policy_metadata():
    response = client.get("/plan?platform=windows&mode=live")
    assert response.status_code == 200

    plan = PlanResponse.model_validate(response.json())

    restart_action = next(action for action in plan.candidate_actions if action.action_type == "restart_service")
    assert restart_action.risk_tier == "medium"
    assert restart_action.approval_required is True
    assert restart_action.execution_mode == "simulate_only"
    assert restart_action.policy_reason
    assert plan.approval_required_actions
    assert plan.blocked_actions
    assert plan.strategy_selections
    first_selection = plan.strategy_selections[0]
    assert first_selection.selected_strategy_id
    assert first_selection.winning_reason
    assert first_selection.ranked_candidates
    assert first_selection.rejected_reasons


def test_plan_includes_trace_and_planning_reasons():
    response = client.get("/plan?platform=linux")
    assert response.status_code == 200

    plan = PlanResponse.model_validate(response.json())
    assert plan.decision_trace
    assert all(action.planning_reason for action in plan.candidate_actions)
    assert all(action.policy_reason for action in plan.candidate_actions)
    assert any(entry.stage == "actions_policy_classified" for entry in plan.decision_trace)


def test_plan_audit_trail_stops_before_dispatch_when_no_execution():
    response = client.get("/plan?platform=linux")
    assert response.status_code == 200

    plan = PlanResponse.model_validate(response.json())
    stage_names = [stage.stage for stage in plan.audit_trail.stages]

    assert stage_names == [
        "runtime_observation_collected",
        "snapshot_collected",
        "issues_detected",
        "issues_scored",
        "actions_planned",
        "actions_policy_classified",
    ]
    assert "actions_dispatched" not in stage_names
    assert "actions_executed" not in stage_names
    assert "actions_verified" not in stage_names


@pytest.mark.parametrize(
    ("platform", "expected_os_name"),
    [
        ("linux", "Linux"),
        ("windows", "Windows"),
        ("macos", "macOS"),
    ],
)
def test_execute_works_for_each_platform(platform: str, expected_os_name: str):
    response = client.get(f"/execute?platform={platform}")
    assert response.status_code == 200

    execution_report = ExecuteResponse.model_validate(response.json())

    assert execution_report.snapshot.system_info.os_name == expected_os_name
    assert len(execution_report.dispatch.executed_actions) >= 1
    assert len(execution_report.verification_results) >= 1
    assert all(result.executed is True for result in execution_report.dispatch.executed_actions)
    assert all(result.success is True for result in execution_report.dispatch.executed_actions)
    assert all(result.dispatch_reason for result in execution_report.dispatch.executed_actions)
    assert execution_report.remediation_strategies
    assert execution_report.incident_states
    assert execution_report.playbook_executions


def test_execute_only_runs_allowed_non_blocked_actions():
    response = client.get("/execute?platform=windows&mode=live")
    assert response.status_code == 200

    execution_report = ExecuteResponse.model_validate(response.json())
    executed_action_types = {result.action_type for result in execution_report.dispatch.executed_actions}

    assert "restart_service" not in executed_action_types
    assert "clear_temp_files" not in executed_action_types
    assert execution_report.execution_halted_by_approval is True
    assert execution_report.approval_halt_reasons
    assert execution_report.decision_trace
    assert any(entry.stage == "actions_dispatched" for entry in execution_report.decision_trace)
    assert any(entry.stage == "actions_verified" for entry in execution_report.decision_trace)
    assert any(state.current_state in {"approval_pending", "denied", "expired", "blocked"} for state in execution_report.incident_states)
    assert execution_report.strategy_selections


def test_execute_audit_trail_includes_dispatch_and_verification_stages():
    response = client.get("/execute?platform=linux")
    assert response.status_code == 200

    execution_report = ExecuteResponse.model_validate(response.json())
    stage_names = [stage.stage for stage in execution_report.audit_trail.stages]

    assert "actions_dispatched" in stage_names
    assert "actions_executed" in stage_names
    assert "actions_verified" in stage_names


def test_execution_response_contains_execution_and_verification_data():
    response = client.get("/execute")
    assert response.status_code == 200

    execution_report = ExecuteResponse.model_validate(response.json())

    assert execution_report.dispatch.executed_actions
    assert execution_report.verification_results
    assert {
        result.action_type for result in execution_report.dispatch.executed_actions
    } == {
        verification.action_type for verification in execution_report.verification_results
    }
    assert execution_report.playbook_executions


def test_plan_macos_live_mode_uses_mocked_live_collector(monkeypatch: pytest.MonkeyPatch):
    live_snapshot = build_mock_live_macos_snapshot()
    monkeypatch.setattr(
        api_routes.state_manager.adapters["macos"],
        "_collect_live_snapshot",
        lambda: live_snapshot,
    )

    response = client.get("/plan?platform=macos&mode=live")
    assert response.status_code == 200

    plan = PlanResponse.model_validate(response.json())
    assert plan.snapshot.system_info.hostname == "live-macos-host"
    assert {action.action_type for action in plan.allowed_actions} == {
        "inspect_process",
        "collect_forensic_snapshot",
    }
    assert plan.remediation_strategies


def test_execute_macos_live_mode_still_simulates_actions(monkeypatch: pytest.MonkeyPatch):
    live_snapshot = build_mock_live_macos_snapshot()
    monkeypatch.setattr(
        api_routes.state_manager.adapters["macos"],
        "_collect_live_snapshot",
        lambda: live_snapshot,
    )

    response = client.get("/execute?platform=macos&mode=live")
    assert response.status_code == 200

    execution_report = ExecuteResponse.model_validate(response.json())
    executed_action_types = {
        result.action_type for result in execution_report.dispatch.executed_actions
    }

    assert execution_report.snapshot.system_info.hostname == "live-macos-host"
    assert executed_action_types == {"inspect_process", "collect_forensic_snapshot"}
    assert "clear_temp_files" not in executed_action_types
    assert all(result.message.startswith("Simulated") for result in execution_report.dispatch.executed_actions)
    assert all(result.success is True for result in execution_report.dispatch.executed_actions)
    assert execution_report.playbook_executions


def test_plan_includes_playbook_and_state_machine_data():
    response = client.get("/plan?platform=linux")
    assert response.status_code == 200
    payload = response.json()
    assert payload["remediation_strategies"]
    assert payload["incident_states"]
    assert payload["remediation_strategies"][0]["playbook"]["steps"]
    assert payload["incident_states"][0]["current_state"] in {
        "approved",
        "approval_pending",
        "denied",
        "expired",
        "blocked",
    }
    assert "approvals" in payload
    assert "approval_summary" in payload


def test_execute_includes_playbook_execution_data():
    response = client.get("/execute?platform=linux")
    assert response.status_code == 200
    payload = response.json()
    assert payload["playbook_executions"]
    assert "verification_checkpoints" in payload["playbook_executions"][0]
    assert "execution_halted_by_approval" in payload
    assert "approval_halt_reasons" in payload


def test_incident_detail_includes_playbook_and_state():
    snapshot_response = client.get("/snapshot?platform=linux")
    assert snapshot_response.status_code == 200
    incidents_response = client.get("/incidents?platform=linux")
    assert incidents_response.status_code == 200
    incidents = incidents_response.json()
    assert incidents

    incident_key = incidents[0]["incident_key"]
    detail_response = client.get(f"/incidents/{incident_key}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["incident_state"] is not None
    assert detail["remediation_strategy"] is not None
    assert detail["strategy_selection"] is not None
    assert detail["playbook_execution"] is not None


def test_graph_current_endpoint_returns_connected_graph_shape():
    response = client.get("/graph/current?platform=linux&mode=mock")
    assert response.status_code == 200

    payload = response.json()
    assert "nodes" in payload
    assert "edges" in payload
    assert "metadata" in payload
    assert payload["nodes"]
    assert payload["edges"]
    assert any(node["type"] == "host" for node in payload["nodes"])
    assert any(node["type"] == "issue" for node in payload["nodes"])
    assert any(node["type"] == "strategy" for node in payload["nodes"])
    assert any(edge["type"] in {"contains", "targets", "listens_on", "executes"} for edge in payload["edges"])


def test_graph_incident_endpoint_returns_incident_scoped_graph_shape():
    snapshot_response = client.get("/snapshot?platform=linux&mode=mock")
    assert snapshot_response.status_code == 200

    incidents_response = client.get("/incidents?platform=linux&mode=mock")
    assert incidents_response.status_code == 200
    incidents = incidents_response.json()
    assert incidents

    incident_key = incidents[0]["incident_key"]
    graph_response = client.get(f"/graph/incident/{incident_key}?mode=mock")
    assert graph_response.status_code == 200
    payload = graph_response.json()

    assert payload["metadata"]["incident_key"] == incident_key
    assert any(node["id"] == f"incident:{incident_key}" for node in payload["nodes"])
    assert any(node["type"] == "issue" for node in payload["nodes"])
    assert any(node["type"] == "strategy" for node in payload["nodes"])
    assert payload["edges"]


def test_playbooks_endpoints_return_definitions():
    all_response = client.get("/playbooks")
    assert all_response.status_code == 200
    all_playbooks = all_response.json()
    assert all_playbooks

    single_response = client.get("/playbooks/SERVICE_DOWN")
    assert single_response.status_code == 200
    playbook = single_response.json()
    assert playbook["issue_type"] == "SERVICE_DOWN"
    assert playbook["steps"]


def test_invalid_platform_returns_clear_400_error():
    response = client.get("/snapshot?platform=solaris")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unsupported platform 'solaris'. Supported platforms: linux, windows, macos."
    }


def test_invalid_mode_returns_clear_400_error():
    response = client.get("/snapshot?platform=macos&mode=turbo")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unsupported mode 'turbo'. Supported modes: mock, live."
    }


def test_runtime_observation_recent_endpoint_returns_trace_payload():
    trace = RuntimeObservationTrace(
        batch=ObservationBatch(
            batch_id="runtime-batch-001",
            platform="macos",
            mode="live",
            requested_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            partial_failure=False,
            task_count=1,
        ),
        results=[
            CommandResult(
                invocation_id="runtime-invocation-001",
                task_id="task-001",
                command_name="hostname",
                args=[],
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                success=True,
                exit_code=0,
                stdout_summary="audit-mac",
                stderr_summary="",
                parsed_artifact_type="hostname",
                parsed_artifact_summary="hostname captured",
            )
        ],
    )
    api_routes.runtime_observation_repository.record_trace(trace)

    response = client.get("/runtime/observations/recent?platform=macos&mode=live")
    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert payload[0]["batch"]["batch_id"] == "runtime-batch-001"
    assert payload[0]["results"][0]["invocation_id"] == "runtime-invocation-001"


def test_runtime_observation_invocation_endpoint_returns_command_result():
    trace = RuntimeObservationTrace(
        batch=ObservationBatch(
            batch_id="runtime-batch-002",
            platform="macos",
            mode="live",
            requested_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            partial_failure=False,
            task_count=1,
        ),
        results=[
            CommandResult(
                invocation_id="runtime-invocation-002",
                task_id="task-002",
                command_name="df",
                args=["-k", "/"],
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                success=True,
                exit_code=0,
                stdout_summary="filesystem parsed",
                stderr_summary="",
                parsed_artifact_type="disk_usage",
                parsed_artifact_summary="50% usage",
            )
        ],
    )
    api_routes.runtime_observation_repository.record_trace(trace)

    response = client.get("/runtime/observations/runtime-invocation-002")
    assert response.status_code == 200
    payload = response.json()
    assert payload["invocation_id"] == "runtime-invocation-002"
    assert payload["command_name"] == "df"


def test_schema_validation():
    payload = {
        "system_info": {
            "hostname": "host",
            "os_name": "linux",
            "os_version": "1.0",
            "uptime_seconds": 100,
        },
        "resources": {
            "cpu_percent": 5.5,
            "memory_total_mb": 4096,
            "memory_used_mb": 1024,
            "disk_total_gb": 100.0,
            "disk_used_gb": 50.0,
            "disk_usage_percent": 50.0,
        },
        "processes": [
            {
                "pid": 1,
                "name": "init",
                "cpu_percent": 0.1,
                "memory_mb": 10.5,
                "status": "running",
            }
        ],
        "services": [
            {
                "name": "svc",
                "status": "running",
                "description": "test",
                "restart_count": 0,
            }
        ],
        "open_ports": [22, 80],
        "recent_logs": ["startup complete"],
        "issues": [
            {
                "id": "issue-1",
                "type": "SERVICE_DOWN",
                "category": "service",
                "description": "Fail",
                "target": "cache",
                "severity": "high",
            }
        ],
    }
    snapshot = StateSnapshot.model_validate(payload)

    assert snapshot.system_info.os_name == "linux"
    assert snapshot.issues[0].type == "SERVICE_DOWN"
    assert snapshot.resources.disk_usage_percent == 50.0
