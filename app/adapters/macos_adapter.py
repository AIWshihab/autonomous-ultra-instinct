import platform as py_platform

from app.adapters.base_adapter import BaseAdapter
from app.core.runtime_observation_service import RuntimeObservationService
from app.models.schemas import (
    ProcessInfo,
    ResourceUsage,
    ServiceInfo,
    StateSnapshot,
    SystemInfo,
)


class MacOSAdapter(BaseAdapter):
    def __init__(self, runtime_observation_service: RuntimeObservationService | None = None) -> None:
        self.runtime_observation_service = runtime_observation_service or RuntimeObservationService()

    def collect_snapshot(self, mode: str = "mock") -> StateSnapshot:
        if mode == "live":
            return self._collect_live_snapshot()
        return self._collect_mock_snapshot()

    def _collect_mock_snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            system_info=SystemInfo(
                hostname="mac-studio.local",
                os_name="macOS",
                os_version="macOS 14.4 Sonoma",
                uptime_seconds=93600,
            ),
            resources=ResourceUsage(
                cpu_percent=17.6,
                memory_total_mb=16384,
                memory_used_mb=9216,
                disk_total_gb=512.0,
                disk_used_gb=287.3,
                disk_usage_percent=56.1,
            ),
            processes=[
                ProcessInfo(pid=312, name="WindowServer", cpu_percent=4.6, memory_mb=284.0, status="running"),
                ProcessInfo(pid=488, name="Finder", cpu_percent=1.1, memory_mb=118.6, status="running"),
                ProcessInfo(pid=706, name="mDNSResponder", cpu_percent=0.4, memory_mb=19.2, status="running"),
                ProcessInfo(pid=5220, name="unsigned-sync-agent", cpu_percent=29.8, memory_mb=244.3, status="running"),
            ],
            services=[
                ServiceInfo(name="Finder", status="running", description="User shell and file manager", restart_count=0),
                ServiceInfo(name="WindowServer", status="running", description="Display server", restart_count=1),
                ServiceInfo(name="mDNSResponder", status="running", description="Bonjour networking service", restart_count=3),
            ],
            open_ports=[53, 5000, 7000],
            recent_logs=[
                "2026-04-16T12:20:03Z mDNSResponder restarted three times in 10 minutes",
                "2026-04-16T12:21:40Z port 5000 listener conflict detected",
                "2026-04-16T12:22:01Z unsigned-sync-agent requested unexpected network access",
            ],
        )

    def _collect_live_snapshot(self) -> StateSnapshot:
        if py_platform.system() != "Darwin":
            return self._collect_mock_snapshot()
        try:
            return self.runtime_observation_service.collect_macos_live_snapshot()
        except Exception as exc:
            snapshot = self._collect_mock_snapshot()
            return snapshot.model_copy(
                update={
                    "recent_logs": [
                        *snapshot.recent_logs,
                        f"runtime observation fallback triggered: {exc}",
                    ]
                }
            )
