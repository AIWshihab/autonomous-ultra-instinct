from app.adapters.base_adapter import BaseAdapter
from app.models.schemas import (
    ProcessInfo,
    ResourceUsage,
    ServiceInfo,
    StateSnapshot,
    SystemInfo,
)


class WindowsAdapter(BaseAdapter):
    def collect_snapshot(self, mode: str = "mock") -> StateSnapshot:
        return StateSnapshot(
            system_info=SystemInfo(
                hostname="win11-workstation",
                os_name="Windows",
                os_version="Windows 11 Pro 23H2",
                uptime_seconds=64800,
            ),
            resources=ResourceUsage(
                cpu_percent=23.1,
                memory_total_mb=32768,
                memory_used_mb=18944,
                disk_total_gb=512.0,
                disk_used_gb=469.0,
                disk_usage_percent=91.6,
            ),
            processes=[
                ProcessInfo(pid=540, name="services.exe", cpu_percent=0.4, memory_mb=32.1, status="running"),
                ProcessInfo(pid=1220, name="explorer.exe", cpu_percent=1.2, memory_mb=156.5, status="running"),
                ProcessInfo(pid=3028, name="MsMpEng.exe", cpu_percent=5.1, memory_mb=312.4, status="running"),
                ProcessInfo(pid=4892, name="temp-updater.exe", cpu_percent=38.7, memory_mb=418.9, status="running"),
            ],
            services=[
                ServiceInfo(name="Spooler", status="unhealthy", description="Print Spooler service", restart_count=3),
                ServiceInfo(name="WinDefend", status="running", description="Windows Defender", restart_count=0),
                ServiceInfo(name="W32Time", status="running", description="Windows Time", restart_count=1),
            ],
            open_ports=[135, 445, 3389],
            recent_logs=[
                "2026-04-16T11:02:10Z Spooler service entered degraded state",
                "2026-04-16T11:04:22Z disk usage crossed warning threshold",
                "2026-04-16T11:05:18Z temp-updater.exe exhibited unusual resource usage",
            ],
        )
