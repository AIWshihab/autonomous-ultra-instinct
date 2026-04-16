import pytest
from fastapi.testclient import TestClient

import app.api.routes as api_routes
from app.main import app
from app.models.schemas import ExecuteResponse, PlanResponse, ProcessInfo, ResourceUsage, StateSnapshot, SystemInfo

client = TestClient(app)


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
    ("platform", "expected_os_name", "expected_allowed_count"),
    [
        ("linux", "Linux", 2),
        ("windows", "Windows", 3),
        ("macos", "macOS", 3),
    ],
)
def test_plan_works_for_each_platform(platform: str, expected_os_name: str, expected_allowed_count: int):
    response = client.get(f"/plan?platform={platform}")
    assert response.status_code == 200

    plan = PlanResponse.model_validate(response.json())

    assert plan.snapshot.system_info.os_name == expected_os_name
    assert len(plan.allowed_actions) == expected_allowed_count
    assert all(action.policy_reason for action in plan.candidate_actions)
    assert all(action.risk_tier for action in plan.candidate_actions)
    assert all(action.execution_mode for action in plan.candidate_actions)
    assert all(action.allowed is True for action in plan.allowed_actions)


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


def test_plan_includes_trace_and_planning_reasons():
    response = client.get("/plan?platform=linux")
    assert response.status_code == 200

    plan = PlanResponse.model_validate(response.json())
    assert plan.decision_trace
    assert all(action.planning_reason for action in plan.candidate_actions)
    assert all(action.policy_reason for action in plan.candidate_actions)
    assert any(entry.stage == "policy" for entry in plan.decision_trace)


@pytest.mark.parametrize(
    ("platform", "expected_os_name", "expected_execution_count"),
    [
        ("linux", "Linux", 2),
        ("windows", "Windows", 3),
        ("macos", "macOS", 3),
    ],
)
def test_execute_works_for_each_platform(platform: str, expected_os_name: str, expected_execution_count: int):
    response = client.get(f"/execute?platform={platform}")
    assert response.status_code == 200

    execution_report = ExecuteResponse.model_validate(response.json())

    assert execution_report.snapshot.system_info.os_name == expected_os_name
    assert len(execution_report.dispatch.executed_actions) == expected_execution_count
    assert len(execution_report.verification_results) == expected_execution_count
    assert all(result.executed is True for result in execution_report.dispatch.executed_actions)
    assert all(result.success is True for result in execution_report.dispatch.executed_actions)
    assert all(result.dispatch_reason for result in execution_report.dispatch.executed_actions)


def test_execute_only_runs_allowed_non_blocked_actions():
    response = client.get("/execute?platform=windows&mode=live")
    assert response.status_code == 200

    execution_report = ExecuteResponse.model_validate(response.json())
    executed_action_types = {result.action_type for result in execution_report.dispatch.executed_actions}

    assert "restart_service" in executed_action_types
    assert "clear_temp_files" not in executed_action_types
    assert execution_report.decision_trace
    assert any(entry.stage == "dispatch" for entry in execution_report.decision_trace)
    assert any(entry.stage == "verification" for entry in execution_report.decision_trace)


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
