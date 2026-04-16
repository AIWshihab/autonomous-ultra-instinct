import subprocess

from app.adapters.macos_adapter import MacOSAdapter
from app.core.runtime_command_policy import RuntimeCommandPolicy
from app.core.runtime_observation_repository import RuntimeObservationRepository
from app.core.runtime_observation_service import RuntimeObservationService


class FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_subprocess_run(command, capture_output, text, check, timeout):  # noqa: ARG001
    command_name = command[0]
    args = command[1:]
    if command_name == "hostname":
        return FakeCompletedProcess(0, "audit-mac\n")
    if command_name == "sw_vers" and args == ["-productVersion"]:
        return FakeCompletedProcess(0, "14.5\n")
    if command_name == "uname" and args == ["-s"]:
        return FakeCompletedProcess(0, "Darwin\n")
    if command_name == "sysctl" and args == ["-n", "kern.boottime"]:
        return FakeCompletedProcess(0, "{ sec = 1710000000, usec = 0 } Thu Mar  9 12:00:00 2024")
    if command_name == "sysctl" and args == ["-n", "hw.memsize"]:
        return FakeCompletedProcess(0, "17179869184\n")
    if command_name == "vm_stat":
        return FakeCompletedProcess(
            0,
            "Mach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 100000.\nPages speculative: 25000.\n",
        )
    if command_name == "ps" and args == ["-A", "-o", "%cpu="]:
        return FakeCompletedProcess(0, "10.0\n20.0\n")
    if command_name == "ps" and args == ["-Arc", "-o", "pid=,comm=,%cpu=,rss=,state="]:
        return FakeCompletedProcess(
            0,
            "312 WindowServer 4.6 290000 R\n488 Finder 1.1 121000 S\n706 mDNSResponder 0.4 19400 S\n",
        )
    if command_name == "df" and args == ["-k", "/"]:
        return FakeCompletedProcess(
            0,
            "Filesystem 1024-blocks Used Available Capacity iused ifree %iused Mounted on\n/dev/disk3s5s1 500000000 250000000 250000000 50% 1234 5678 0% /\n",
        )
    if command_name == "lsof" and args == ["-nP", "-iTCP", "-sTCP:LISTEN"]:
        return FakeCompletedProcess(
            0,
            "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\nmDNSRespo 706 user 12u IPv4 0x123 0t0 TCP *:53 (LISTEN)\npython3 900 user 10u IPv4 0x456 0t0 TCP *:5000 (LISTEN)\n",
        )
    return FakeCompletedProcess(1, "", f"unexpected command: {command}")


def test_allowlisted_command_acceptance():
    policy = RuntimeCommandPolicy()
    decision = policy.decide(
        command_name="hostname",
        args=[],
        platform="macos",
        mode="live",
    )
    assert decision.allowed is True
    assert decision.safety_class == "identity"


def test_blocked_command_rejection():
    policy = RuntimeCommandPolicy()
    decision = policy.decide(
        command_name="rm",
        args=["-rf", "/tmp/foo"],
        platform="macos",
        mode="live",
    )
    assert decision.allowed is False
    assert "not allowlisted" in decision.reason


def test_observation_task_to_command_mapping():
    service = RuntimeObservationService()
    specs = service.task_command_specs("collect_system_identity")
    assert ("hostname", [], "hostname") in specs
    assert ("sw_vers", ["-productVersion"], "os_version") in specs
    assert ("uname", ["-s"], "os_name") in specs


def test_command_parsing_behavior(monkeypatch):
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/sbin/lsof" if name == "lsof" else None)
    service = RuntimeObservationService()

    trace, artifacts = service.run_tasks(
        platform="macos",
        mode="live",
        task_names=[
            "collect_system_identity",
            "collect_resource_usage",
            "collect_processes",
            "collect_open_ports",
            "collect_disk_usage",
        ],
    )

    assert trace.batch.platform == "macos"
    assert "collect_system_identity" in artifacts
    assert artifacts["collect_system_identity"]["hostname"] == "audit-mac"
    assert artifacts["collect_resource_usage"]["memory_total_mb"] > 0
    assert len(artifacts["collect_processes"]) >= 2
    assert artifacts["collect_open_ports"]


def test_macos_live_snapshot_integration(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/sbin/lsof" if name == "lsof" else None)
    runtime_repository = RuntimeObservationRepository(db_path=tmp_path / "history.db")
    runtime_service = RuntimeObservationService(repository=runtime_repository)
    adapter = MacOSAdapter(runtime_observation_service=runtime_service)
    monkeypatch.setattr("platform.system", lambda: "Darwin")

    snapshot = adapter.collect_snapshot(mode="live")

    assert snapshot.system_info.hostname == "audit-mac"
    assert snapshot.runtime_observation_trace is not None
    assert snapshot.runtime_observation_trace.results


def test_command_trace_payload_shape_and_persistence(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/sbin/lsof" if name == "lsof" else None)
    repository = RuntimeObservationRepository(db_path=tmp_path / "history.db")
    service = RuntimeObservationService(repository=repository)

    trace, _ = service.run_tasks(
        platform="macos",
        mode="live",
        task_names=RuntimeObservationService.DEFAULT_TASKS,
    )

    assert trace.results
    sample = trace.results[0]
    assert sample.invocation_id
    assert sample.task_id
    assert sample.command_name
    assert isinstance(sample.args, list)
    assert sample.started_at
    assert sample.finished_at
    assert isinstance(sample.success, bool)
    assert isinstance(sample.exit_code, int)
    assert sample.stdout_summary is not None
    assert sample.stderr_summary is not None

    recent = repository.list_recent_traces(limit=5, platform="macos", mode="live")
    assert recent
    fetched = repository.get_result(sample.invocation_id)
    assert fetched is not None
    assert fetched.invocation_id == sample.invocation_id
