from app.core.scoring import ScoringEngine
from app.adapters.linux_adapter import LinuxAdapter
from app.adapters.macos_adapter import MacOSAdapter
from app.adapters.windows_adapter import WindowsAdapter
from app.detectors.rule_based import RuleBasedDetector
from app.models.schemas import ProcessInfo, ResourceUsage, ServiceInfo, StateSnapshot, SystemInfo


def build_snapshot(
    *,
    disk_usage_percent: float = 40.0,
    processes: list[ProcessInfo] | None = None,
    services: list[ServiceInfo] | None = None,
    recent_logs: list[str] | None = None,
) -> StateSnapshot:
    disk_total_gb = 100.0
    disk_used_gb = round((disk_usage_percent / 100) * disk_total_gb, 1)
    return StateSnapshot(
        system_info=SystemInfo(
            hostname="detector-host",
            os_name="linux",
            os_version="test",
            uptime_seconds=100,
        ),
        resources=ResourceUsage(
            cpu_percent=12.0,
            memory_total_mb=8192,
            memory_used_mb=2048,
            disk_total_gb=disk_total_gb,
            disk_used_gb=disk_used_gb,
            disk_usage_percent=disk_usage_percent,
        ),
        processes=processes or [],
        services=services or [],
        open_ports=[],
        recent_logs=recent_logs or [],
    )


def test_detector_creates_disk_pressure_issue():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(disk_usage_percent=93.0)

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "DISK_PRESSURE")
    assert issue.severity == "high"
    assert issue.confidence == 0.94
    assert issue.priority_score > 0
    assert issue.evidence == ["disk usage is 93.0%"]
    assert issue.detection_reason == "Disk usage exceeded the V1 threshold of 90%."
    assert issue.severity_reason == "Disk usage at or above 95% is classified as critical."
    assert issue.confidence_reason == "Disk percentage is a direct measured signal."


def test_detector_creates_critical_disk_pressure_issue_at_95_percent():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(disk_usage_percent=96.0)

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "DISK_PRESSURE")
    assert issue.severity == "critical"


def test_detector_creates_service_down_issue():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(
        services=[ServiceInfo(name="ssh", status="failed", description="SSH", restart_count=1)]
    )

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "SERVICE_DOWN")
    assert issue.target == "ssh"
    assert issue.severity == "high"
    assert issue.confidence == 0.96
    assert issue.evidence == ["service ssh status=failed"]
    assert issue.detection_reason == "A monitored service is not healthy."
    assert issue.severity_reason == "Service unavailability is high severity in V1."
    assert issue.confidence_reason == "Service status is directly observable."


def test_detector_creates_crash_loop_issue():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(
        services=[ServiceInfo(name="Spooler", status="running", description="Print", restart_count=3)]
    )

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "CRASH_LOOP")
    assert issue.target == "Spooler"
    assert issue.severity == "high"
    assert issue.confidence == 0.85


def test_detector_creates_high_resource_usage_issue():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(
        processes=[ProcessInfo(pid=22, name="hot-process", cpu_percent=84.5, memory_mb=120.0, status="running")]
    )

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "HIGH_RESOURCE_USAGE")
    assert issue.target == "pid:22"
    assert issue.severity == "medium"
    assert issue.confidence == 0.9


def test_detector_marks_extreme_cpu_high_resource_usage_as_high():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(
        processes=[ProcessInfo(pid=23, name="hotter-process", cpu_percent=97.0, memory_mb=120.0, status="running")]
    )

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "HIGH_RESOURCE_USAGE")
    assert issue.severity == "high"
    assert issue.confidence == 0.95


def test_detector_creates_suspicious_process_issue():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(
        processes=[ProcessInfo(pid=77, name="temp-updater.exe", cpu_percent=5.0, memory_mb=50.0, status="running")]
    )

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "SUSPICIOUS_PROCESS")
    assert issue.target == "pid:77"
    assert issue.severity == "medium"
    assert issue.confidence == 0.52


def test_detector_marks_stronger_suspicious_process_as_high_confidence():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(
        processes=[ProcessInfo(pid=78, name="unsigned-sync-agent", cpu_percent=5.0, memory_mb=50.0, status="running")]
    )

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "SUSPICIOUS_PROCESS")
    assert issue.severity == "high"
    assert issue.confidence == 0.68


def test_detector_creates_port_conflict_issue_from_logs():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(
        recent_logs=["2026-04-16T09:15:03Z port 8080 reported as already in use"]
    )

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "PORT_CONFLICT")
    assert issue.target == "port:8080"
    assert issue.severity == "medium"
    assert issue.confidence == 0.8


def test_detector_marks_repeated_port_conflict_as_high():
    detector = RuleBasedDetector()
    snapshot = build_snapshot(
        recent_logs=[
            "2026-04-16T09:15:03Z port 8080 reported as already in use",
            "2026-04-16T09:15:14Z port 8080 listener conflict detected",
        ]
    )

    issues = detector.detect(snapshot)

    issue = next(issue for issue in issues if issue.type == "PORT_CONFLICT")
    assert issue.severity == "high"
    assert issue.confidence == 0.89


def test_priority_score_ranks_more_severe_and_confident_issues_higher():
    scoring = ScoringEngine()

    critical_disk = scoring.score_disk_pressure(97.0)
    medium_port = scoring.score_port_conflict(1)

    assert critical_disk["priority_score"] > medium_port["priority_score"]


def test_health_and_risk_scores_and_issue_summary_are_computed():
    detector = RuleBasedDetector()
    scoring = ScoringEngine()
    snapshot = build_snapshot(
        disk_usage_percent=96.0,
        processes=[ProcessInfo(pid=78, name="unsigned-sync-agent", cpu_percent=5.0, memory_mb=50.0, status="running")],
        services=[ServiceInfo(name="ssh", status="failed", description="SSH", restart_count=3)],
        recent_logs=["2026-04-16T09:15:03Z port 8080 reported as already in use"],
    )

    issues = detector.detect(snapshot)
    health_score, risk_score, summary = scoring.summarize_issues(issues)

    assert health_score < 100
    assert risk_score > 0
    assert summary.critical_count == 1
    assert summary.high_count >= 2
    assert summary.medium_count >= 1
    assert summary.total_count == len(issues)


def test_mock_adapters_do_not_hardcode_issues():
    adapters = [LinuxAdapter(), WindowsAdapter(), MacOSAdapter()]

    snapshots = [adapter.collect_snapshot() for adapter in adapters]

    assert all(snapshot.issues == [] for snapshot in snapshots)
