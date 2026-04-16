import pytest
from fastapi.testclient import TestClient

import app.api.routes as api_routes
from app.core.baseline_service import BaselineService
from app.core.correlation_service import CorrelationService
from app.core.history_repository import HistoryRepository
from app.core.history_service import HistoryService
from app.main import app
from app.models.schemas import (
    BaselineSummary,
    ProcessInfo,
    ResourceUsage,
    ServiceInfo,
    StateSnapshot,
    SystemInfo,
)

client = TestClient(app)


def build_test_services(tmp_path):
    repository = HistoryRepository(db_path=tmp_path / "history.db")
    history_service = HistoryService(repository=repository)
    baseline_service = BaselineService(repository=repository)
    api_routes.history_service = history_service
    api_routes.baseline_service = baseline_service
    api_routes.correlation_service = CorrelationService(repository=repository)
    return history_service, baseline_service


def build_snapshot(hostname="baseline-host", cpu=12.0, memory=1024.0, disk=35.0, process_names=None, service_status="running") -> StateSnapshot:
    process_names = process_names or ["agent-daemon", "ssh", "kernel-task"]
    return StateSnapshot(
        system_info=SystemInfo(
            hostname=hostname,
            os_name="Linux",
            os_version="Ubuntu 22.04",
            uptime_seconds=12000,
        ),
        resources=ResourceUsage(
            cpu_percent=cpu,
            memory_total_mb=4096,
            memory_used_mb=memory,
            disk_total_gb=256.0,
            disk_used_gb=disk * 2.56,
            disk_usage_percent=disk,
        ),
        processes=[
            ProcessInfo(pid=i + 100, name=name, cpu_percent=5.0 + i * 2.0, memory_mb=50.0 + i * 5.0, status="running")
            for i, name in enumerate(process_names)
        ],
        services=[ServiceInfo(name="AuthService", status=service_status, description="Auth manager", restart_count=0)],
        open_ports=[22, 80],
        recent_logs=["baseline snapshot log entry"],
    )


def test_baseline_computation_from_stored_history(tmp_path, monkeypatch):
    history_service, baseline_service = build_test_services(tmp_path)

    history_service.record_snapshot_event(build_snapshot(cpu=10.0, memory=1100.0, disk=30.0), "linux", "mock")
    history_service.record_snapshot_event(build_snapshot(cpu=12.0, memory=1200.0, disk=32.0), "linux", "mock")

    current_snapshot = build_snapshot(cpu=35.0, memory=1300.0, disk=42.0)
    monkeypatch.setattr(api_routes.state_manager.adapters["linux"], "collect_snapshot", lambda mode: current_snapshot)

    response = client.get("/baseline/current?platform=linux&mode=mock")
    assert response.status_code == 200

    baseline = BaselineSummary.model_validate(response.json())
    assert baseline.host_baseline.platform == "linux"
    assert baseline.host_baseline.event_count == 2
    assert baseline.host_baseline.avg_cpu_percent == pytest.approx(11.0, abs=0.1)
    assert any(signal.signal_type == "cpu_above_baseline" for signal in baseline.deviation_signals)
    assert any(signal.signal_type == "disk_above_baseline" for signal in baseline.deviation_signals)


def test_unseen_process_and_service_regression_in_snapshot_response(tmp_path, monkeypatch):
    history_service, baseline_service = build_test_services(tmp_path)

    history_service.record_snapshot_event(build_snapshot(cpu=10.0, process_names=["agent-daemon", "ssh"], service_status="running"), "linux", "mock")
    history_service.record_snapshot_event(build_snapshot(cpu=11.0, process_names=["agent-daemon", "ssh"], service_status="running"), "linux", "mock")

    current_snapshot = build_snapshot(
        cpu=28.0,
        process_names=["agent-daemon", "ssh", "unknown-helper"],
        service_status="failed",
    )
    monkeypatch.setattr(api_routes.state_manager.adapters["linux"], "collect_snapshot", lambda mode: current_snapshot)

    response = client.get("/snapshot?platform=linux&mode=mock")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())
    assert snapshot.baseline_summary is not None
    assert snapshot.baseline_summary.host_baseline.event_count == 2
    assert any(signal.signal_type == "unseen_process" for signal in snapshot.baseline_summary.deviation_signals)
    assert any(signal.signal_type == "service_health_regression" for signal in snapshot.baseline_summary.deviation_signals)
    assert any(issue.deviation_score > 0 for issue in snapshot.issues)
    assert any(issue.anomaly_reason for issue in snapshot.issues)


def test_baseline_adjusts_issue_confidence_and_priority(tmp_path, monkeypatch):
    history_service, baseline_service = build_test_services(tmp_path)

    history_service.record_snapshot_event(build_snapshot(cpu=10.0, process_names=["agent-daemon", "ssh"]), "linux", "mock")
    history_service.record_snapshot_event(build_snapshot(cpu=10.5, process_names=["agent-daemon", "ssh"]), "linux", "mock")

    current_snapshot = build_snapshot(cpu=90.0, process_names=["agent-daemon", "ssh"], service_status="running")
    current_snapshot.processes[0].cpu_percent = 92.0
    monkeypatch.setattr(api_routes.state_manager.adapters["linux"], "collect_snapshot", lambda mode: current_snapshot)

    response = client.get("/snapshot?platform=linux&mode=mock")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())
    high_resource_issues = [issue for issue in snapshot.issues if issue.type == "HIGH_RESOURCE_USAGE"]
    assert high_resource_issues
    issue = high_resource_issues[0]
    assert issue.deviation_score > 0
    assert issue.confidence >= 0.9
    assert issue.priority_score >= 20


def test_api_snapshot_includes_baseline_summary(tmp_path, monkeypatch):
    history_service, baseline_service = build_test_services(tmp_path)

    history_service.record_snapshot_event(build_snapshot(cpu=15.0), "linux", "mock")
    current_snapshot = build_snapshot(cpu=25.0)
    monkeypatch.setattr(api_routes.state_manager.adapters["linux"], "collect_snapshot", lambda mode: current_snapshot)

    response = client.get("/snapshot?platform=linux&mode=mock")
    assert response.status_code == 200

    snapshot = StateSnapshot.model_validate(response.json())
    assert snapshot.baseline_summary is not None
    assert snapshot.baseline_summary.host_baseline.platform == "linux"
    assert snapshot.baseline_summary.baseline_comparisons
    assert isinstance(snapshot.baseline_summary.deviation_signals, list)
