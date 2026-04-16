import os
import platform as py_platform
import re
import shutil
import socket
import subprocess
from typing import List

from app.adapters.base_adapter import BaseAdapter
from app.models.schemas import (
    ProcessInfo,
    ResourceUsage,
    ServiceInfo,
    StateSnapshot,
    SystemInfo,
)


class MacOSAdapter(BaseAdapter):
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

        hostname = socket.gethostname()
        os_version = self._safe_run(["sw_vers", "-productVersion"]) or py_platform.mac_ver()[0] or "unknown"
        uptime_seconds = self._read_uptime_seconds()
        total_memory_mb = self._read_total_memory_mb()
        used_memory_mb = self._read_used_memory_mb(total_memory_mb)
        cpu_percent = self._read_cpu_percent()
        disk_total_gb, disk_used_gb, disk_usage_percent = self._read_disk_usage()
        processes = self._read_processes()
        open_ports = self._read_open_ports()
        services = self._build_live_services(processes)
        recent_logs = ["live macOS snapshot collected in read-only mode"]

        return StateSnapshot(
            system_info=SystemInfo(
                hostname=hostname,
                os_name="macOS",
                os_version=f"macOS {os_version}",
                uptime_seconds=uptime_seconds,
            ),
            resources=ResourceUsage(
                cpu_percent=cpu_percent,
                memory_total_mb=total_memory_mb,
                memory_used_mb=used_memory_mb,
                disk_total_gb=disk_total_gb,
                disk_used_gb=disk_used_gb,
                disk_usage_percent=disk_usage_percent,
            ),
            processes=processes,
            services=services,
            open_ports=open_ports,
            recent_logs=recent_logs,
        )

    def _safe_run(self, command: list[str]) -> str | None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if result.returncode != 0:
            return None

        output = result.stdout.strip()
        return output or None

    def _read_uptime_seconds(self) -> int:
        boot_time_output = self._safe_run(["sysctl", "-n", "kern.boottime"])
        if not boot_time_output:
            return 0

        match = re.search(r"sec = (\d+)", boot_time_output)
        if not match:
            return 0

        try:
            boot_time_seconds = int(match.group(1))
        except ValueError:
            return 0

        current_time_output = self._safe_run(["date", "+%s"])
        if not current_time_output:
            return 0

        try:
            current_time_seconds = int(current_time_output)
        except ValueError:
            return 0

        return max(0, current_time_seconds - boot_time_seconds)

    def _read_total_memory_mb(self) -> int:
        memsize_output = self._safe_run(["sysctl", "-n", "hw.memsize"])
        if not memsize_output:
            return 0

        try:
            return int(int(memsize_output) / (1024 * 1024))
        except ValueError:
            return 0

    def _read_used_memory_mb(self, total_memory_mb: int) -> int:
        vm_stat_output = self._safe_run(["vm_stat"])
        if not vm_stat_output or total_memory_mb <= 0:
            return 0

        page_size_match = re.search(r"page size of (\d+) bytes", vm_stat_output)
        page_size = int(page_size_match.group(1)) if page_size_match else 4096
        free_pages = self._extract_vm_stat_pages(vm_stat_output, "Pages free")
        speculative_pages = self._extract_vm_stat_pages(vm_stat_output, "Pages speculative")

        free_memory_mb = int(((free_pages + speculative_pages) * page_size) / (1024 * 1024))
        return max(0, min(total_memory_mb, total_memory_mb - free_memory_mb))

    def _extract_vm_stat_pages(self, vm_stat_output: str, label: str) -> int:
        match = re.search(rf"{re.escape(label)}:\s+(\d+)\.", vm_stat_output)
        if not match:
            return 0
        return int(match.group(1))

    def _read_cpu_percent(self) -> float:
        ps_output = self._safe_run(["ps", "-A", "-o", "%cpu="])
        if not ps_output:
            return 0.0

        cpu_total = 0.0
        for line in ps_output.splitlines():
            try:
                cpu_total += float(line.strip())
            except ValueError:
                continue

        cpu_count = max(1, os_cpu_count())
        normalized_cpu = cpu_total / cpu_count
        return round(max(0.0, min(100.0, normalized_cpu)), 1)

    def _read_disk_usage(self) -> tuple[float, float, float]:
        total_bytes, used_bytes, _ = shutil.disk_usage("/")
        disk_total_gb = round(total_bytes / (1024 ** 3), 1)
        disk_used_gb = round(used_bytes / (1024 ** 3), 1)
        disk_usage_percent = round((used_bytes / total_bytes) * 100, 1) if total_bytes else 0.0
        return disk_total_gb, disk_used_gb, disk_usage_percent

    def _read_processes(self) -> List[ProcessInfo]:
        ps_output = self._safe_run(["ps", "-Arc", "-o", "pid=,comm=,%cpu=,rss=,state="])
        if not ps_output:
            return []

        processes: List[ProcessInfo] = []
        for line in ps_output.splitlines()[:5]:
            parts = line.split(None, 4)
            if len(parts) != 5:
                continue

            pid_text, name, cpu_text, rss_text, state_text = parts
            try:
                pid = int(pid_text)
                cpu_percent = float(cpu_text)
                memory_mb = round(int(rss_text) / 1024, 1)
            except ValueError:
                continue

            processes.append(
                ProcessInfo(
                    pid=pid,
                    name=name,
                    cpu_percent=cpu_percent,
                    memory_mb=memory_mb,
                    status=self._normalize_process_state(state_text),
                )
            )

        return processes

    def _normalize_process_state(self, state_text: str) -> str:
        state_prefix = state_text[:1]
        mapping = {
            "R": "running",
            "S": "sleeping",
            "I": "idle",
            "T": "stopped",
            "Z": "zombie",
            "U": "waiting",
        }
        return mapping.get(state_prefix, "running")

    def _read_open_ports(self) -> List[int]:
        if shutil.which("lsof"):
            lsof_output = self._safe_run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"])
            if lsof_output:
                ports = self._parse_lsof_ports(lsof_output)
                if ports:
                    return ports

        netstat_output = self._safe_run(["netstat", "-anv", "-p", "tcp"])
        if not netstat_output:
            return []

        ports: List[int] = []
        for line in netstat_output.splitlines():
            if "LISTEN" not in line:
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            local_address = parts[3]
            try:
                port = int(local_address.rsplit(".", 1)[1])
            except (IndexError, ValueError):
                continue
            ports.append(port)

        return sorted(set(ports))[:20]

    def _parse_lsof_ports(self, lsof_output: str) -> List[int]:
        ports: List[int] = []
        for line in lsof_output.splitlines()[1:]:
            match = re.search(r":(\d+)\s+\(LISTEN\)", line)
            if not match:
                continue
            ports.append(int(match.group(1)))
        return sorted(set(ports))[:20]

    def _build_live_services(self, processes: List[ProcessInfo]) -> List[ServiceInfo]:
        preferred_names = {"Finder", "WindowServer", "mDNSResponder"}
        services: List[ServiceInfo] = []
        for process in processes:
            if process.name not in preferred_names:
                continue
            services.append(
                ServiceInfo(
                    name=process.name,
                    status="running",
                    description="Observed from live macOS process list",
                    restart_count=0,
                )
            )
        return services

def os_cpu_count() -> int:
    return os.cpu_count() or 1
