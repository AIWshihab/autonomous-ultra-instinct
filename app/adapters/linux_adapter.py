from app.adapters.base_adapter import BaseAdapter
from app.models.schemas import (
    ProcessInfo,
    ResourceUsage,
    ServiceInfo,
    StateSnapshot,
    SystemInfo,
)


class LinuxAdapter(BaseAdapter):
    def collect_snapshot(self, mode: str = "mock") -> StateSnapshot:
        return StateSnapshot(
            system_info=SystemInfo(
                hostname="linux-node-01",
                os_name="Linux",
                os_version="Ubuntu 22.04.4 LTS",
                uptime_seconds=172800,
            ),
            resources=ResourceUsage(
                cpu_percent=19.4,
                memory_total_mb=16384,
                memory_used_mb=7424,
                disk_total_gb=256.0,
                disk_used_gb=141.7,
                disk_usage_percent=55.4,
            ),
            processes=[
                ProcessInfo(pid=1, name="systemd", cpu_percent=0.1, memory_mb=18.5, status="running"),
                ProcessInfo(pid=942, name="sshd", cpu_percent=0.2, memory_mb=14.8, status="running"),
                ProcessInfo(pid=1884, name="nginx", cpu_percent=0.9, memory_mb=46.2, status="running"),
                ProcessInfo(pid=2660, name="dockerd", cpu_percent=1.8, memory_mb=128.0, status="running"),
            ],
            services=[
                ServiceInfo(name="nginx", status="running", description="Web server", restart_count=1),
                ServiceInfo(name="docker", status="running", description="Container runtime", restart_count=0),
                ServiceInfo(name="ssh", status="unhealthy", description="Secure shell service", restart_count=2),
            ],
            open_ports=[22, 80, 443, 8080],
            recent_logs=[
                "2026-04-16T09:11:12Z nginx health check passed",
                "2026-04-16T09:14:45Z ssh health probe failed",
                "2026-04-16T09:15:03Z port 8080 reported as already in use",
            ],
        )
