from app.adapters.macos_adapter import MacOSAdapter
from app.models.schemas import ResourceUsage, StateSnapshot, SystemInfo


def test_macos_adapter_live_mode_can_be_mocked(monkeypatch):
    adapter = MacOSAdapter()
    live_snapshot = StateSnapshot(
        system_info=SystemInfo(
            hostname="direct-live-mac",
            os_name="macOS",
            os_version="macOS 14.5",
            uptime_seconds=120,
        ),
        resources=ResourceUsage(
            cpu_percent=7.5,
            memory_total_mb=8192,
            memory_used_mb=4096,
            disk_total_gb=256.0,
            disk_used_gb=128.0,
            disk_usage_percent=50.0,
        ),
    )

    monkeypatch.setattr(adapter, "_collect_live_snapshot", lambda: live_snapshot)

    snapshot = adapter.collect_snapshot(mode="live")

    assert snapshot.system_info.hostname == "direct-live-mac"
    assert snapshot.system_info.os_name == "macOS"
