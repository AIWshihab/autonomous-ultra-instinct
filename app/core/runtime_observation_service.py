from __future__ import annotations

import os
import platform as py_platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

from app.core.runtime_command_policy import RuntimeCommandPolicy
from app.core.runtime_observation_repository import RuntimeObservationRepository
from app.models.schemas import (
    CommandInvocation,
    CommandPolicyDecision,
    CommandResult,
    ObservationBatch,
    ObservationTask,
    ProcessInfo,
    ResourceUsage,
    RuntimeObservationTrace,
    ServiceInfo,
    StateSnapshot,
    SystemInfo,
)


class RuntimeObservationService:
    DEFAULT_TASKS = [
        "collect_system_identity",
        "collect_resource_usage",
        "collect_processes",
        "collect_open_ports",
        "collect_disk_usage",
    ]

    def __init__(
        self,
        policy: RuntimeCommandPolicy | None = None,
        repository: RuntimeObservationRepository | None = None,
    ) -> None:
        self.policy = policy or RuntimeCommandPolicy()
        self.repository = repository or RuntimeObservationRepository()

    def collect_macos_live_snapshot(self) -> StateSnapshot:
        trace, artifacts = self.run_tasks(
            platform="macos",
            mode="live",
            task_names=self.DEFAULT_TASKS,
        )

        identity = artifacts.get("collect_system_identity", {})
        resources = artifacts.get("collect_resource_usage", {})
        disk = artifacts.get("collect_disk_usage", {})
        processes = artifacts.get("collect_processes", [])
        open_ports = artifacts.get("collect_open_ports", [])
        services = self._derive_services(processes)
        recent_logs = [f"runtime batch {trace.batch.batch_id} collected with strict allowlist orchestration"]
        recent_logs.extend(trace.warnings[:5])

        return StateSnapshot(
            system_info=SystemInfo(
                hostname=str(identity.get("hostname", "unknown")),
                os_name=str(identity.get("os_name", "macOS")),
                os_version=str(identity.get("os_version", "macOS unknown")),
                uptime_seconds=int(identity.get("uptime_seconds", 0)),
            ),
            resources=ResourceUsage(
                cpu_percent=float(resources.get("cpu_percent", 0.0)),
                memory_total_mb=int(resources.get("memory_total_mb", 0)),
                memory_used_mb=int(resources.get("memory_used_mb", 0)),
                disk_total_gb=float(disk.get("disk_total_gb", 0.0)),
                disk_used_gb=float(disk.get("disk_used_gb", 0.0)),
                disk_usage_percent=float(disk.get("disk_usage_percent", 0.0)),
            ),
            processes=processes,
            services=services,
            open_ports=open_ports,
            recent_logs=recent_logs,
            runtime_observation_trace=trace,
        )

    def run_tasks(
        self,
        *,
        platform: str,
        mode: str,
        task_names: list[str],
    ) -> tuple[RuntimeObservationTrace, dict[str, Any]]:
        started_at = datetime.now(timezone.utc)
        batch = ObservationBatch(
            batch_id=self._new_batch_id(),
            platform=platform,
            mode=mode,
            requested_at=started_at,
            task_count=len(task_names),
        )
        tasks: list[ObservationTask] = []
        decisions: list[CommandPolicyDecision] = []
        invocations: list[CommandInvocation] = []
        results: list[CommandResult] = []
        warnings: list[str] = []
        artifact_by_task: dict[str, Any] = {}

        for index, task_name in enumerate(task_names, start=1):
            task = ObservationTask(
                task_id=f"{batch.batch_id}:{index:02d}",
                task_name=task_name,
                requested_at=datetime.now(timezone.utc),
                status="pending",
            )
            command_specs = self.task_command_specs(task_name)
            raw_outputs: dict[str, str] = {}
            task_success = True
            for command_name, args, output_key in command_specs:
                decision = self.policy.decide(
                    command_name=command_name,
                    args=args,
                    platform=platform,
                    mode=mode,
                )
                decisions.append(decision)
                invocation = CommandInvocation(
                    invocation_id=self._new_invocation_id(),
                    task_id=task.task_id,
                    command_name=command_name,
                    args=args,
                    started_at=datetime.now(timezone.utc),
                )
                if not decision.allowed:
                    invocation.finished_at = datetime.now(timezone.utc)
                    invocation.success = False
                    invocation.exit_code = -1
                    invocation.stderr_summary = decision.reason
                    invocation.parsed_artifact_type = output_key
                    invocation.parsed_artifact_summary = "blocked by runtime command policy"
                    invocations.append(invocation)
                    result = CommandResult(
                        invocation_id=invocation.invocation_id,
                        task_id=task.task_id,
                        command_name=command_name,
                        args=args,
                        started_at=invocation.started_at,
                        finished_at=invocation.finished_at,
                        success=False,
                        exit_code=-1,
                        stdout_summary="",
                        stderr_summary=decision.reason,
                        parsed_artifact_type=output_key,
                        parsed_artifact_summary="blocked by runtime command policy",
                    )
                    results.append(result)
                    task.command_invocation_ids.append(invocation.invocation_id)
                    task_success = False
                    warnings.append(
                        f"{task_name} blocked command {command_name} {args}: {decision.reason}"
                    )
                    continue

                run_result = self._run_command(command_name, args)
                invocation.finished_at = run_result["finished_at"]
                invocation.success = run_result["success"]
                invocation.exit_code = run_result["exit_code"]
                invocation.stdout_summary = run_result["stdout_summary"]
                invocation.stderr_summary = run_result["stderr_summary"]
                invocation.parsed_artifact_type = output_key
                invocation.parsed_artifact_summary = (
                    "command output captured" if run_result["success"] else "command execution failed"
                )
                invocations.append(invocation)
                task.command_invocation_ids.append(invocation.invocation_id)
                results.append(
                    CommandResult(
                        invocation_id=invocation.invocation_id,
                        task_id=task.task_id,
                        command_name=command_name,
                        args=args,
                        started_at=invocation.started_at,
                        finished_at=invocation.finished_at,
                        success=run_result["success"],
                        exit_code=run_result["exit_code"],
                        stdout_summary=run_result["stdout_summary"],
                        stderr_summary=run_result["stderr_summary"],
                        parsed_artifact_type=output_key,
                        parsed_artifact_summary=invocation.parsed_artifact_summary,
                    )
                )
                if run_result["success"]:
                    raw_outputs[output_key] = run_result["stdout"]
                else:
                    task_success = False
                    warnings.append(
                        f"{task_name} command {command_name} failed with exit_code={run_result['exit_code']}"
                    )

            parsed_artifact, artifact_type, artifact_summary = self._parse_task_output(task_name, raw_outputs)
            task.parsed_artifact_type = artifact_type
            task.parsed_artifact_summary = artifact_summary
            if parsed_artifact is None:
                task.status = "failed" if not task_success else "partial_failure"
                task.status_reason = "Task parser could not produce a structured artifact."
                warnings.append(f"{task_name} parser failed to produce structured artifact.")
            else:
                artifact_by_task[task_name] = parsed_artifact
                if task_success:
                    task.status = "success"
                    task.status_reason = "All allowlisted commands succeeded."
                else:
                    task.status = "partial_failure"
                    task.status_reason = "Partial command failures occurred but parser produced structured artifact."
            task.finished_at = datetime.now(timezone.utc)
            tasks.append(task)

        finished_at = datetime.now(timezone.utc)
        batch = batch.model_copy(
            update={
                "finished_at": finished_at,
                "partial_failure": any(task.status != "success" for task in tasks),
            }
        )
        trace = RuntimeObservationTrace(
            batch=batch,
            tasks=tasks,
            allowed_commands=self.policy.allowlist(),
            policy_decisions=decisions,
            invocations=invocations,
            results=results,
            warnings=warnings,
        )
        self.repository.record_trace(trace)
        return trace, artifact_by_task

    def task_command_specs(self, task_name: str) -> list[tuple[str, list[str], str]]:
        mapping: dict[str, list[tuple[str, list[str], str]]] = {
            "collect_system_identity": [
                ("hostname", [], "hostname"),
                ("sw_vers", ["-productVersion"], "os_version"),
                ("uname", ["-s"], "os_name"),
                ("sysctl", ["-n", "kern.boottime"], "boot_time"),
            ],
            "collect_resource_usage": [
                ("sysctl", ["-n", "hw.memsize"], "memory_total"),
                ("vm_stat", [], "vm_stat"),
                ("ps", ["-A", "-o", "%cpu="], "cpu_lines"),
            ],
            "collect_processes": [
                ("ps", ["-Arc", "-o", "pid=,comm=,%cpu=,rss=,state="], "process_table"),
            ],
            "collect_open_ports": [
                (
                    "lsof",
                    ["-nP", "-iTCP", "-sTCP:LISTEN"],
                    "lsof_ports",
                )
                if shutil.which("lsof")
                else ("netstat", ["-anv", "-p", "tcp"], "netstat_ports"),
            ],
            "collect_disk_usage": [
                ("df", ["-k", "/"], "disk_df"),
            ],
        }
        if task_name not in mapping:
            return []
        return mapping[task_name]

    def list_recent_observations(
        self,
        *,
        limit: int = 20,
        platform: str | None = None,
        mode: str | None = None,
    ) -> list[RuntimeObservationTrace]:
        return self.repository.list_recent_traces(limit=limit, platform=platform, mode=mode)

    def get_invocation_result(self, invocation_id: str) -> CommandResult | None:
        return self.repository.get_result(invocation_id)

    def _run_command(self, command_name: str, args: list[str]) -> dict[str, Any]:
        command = [command_name, *args]
        started_at = datetime.now(timezone.utc)
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
            finished_at = datetime.now(timezone.utc)
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            return {
                "success": proc.returncode == 0,
                "exit_code": int(proc.returncode),
                "stdout": stdout,
                "stderr": stderr,
                "stdout_summary": self._summarize_text(stdout),
                "stderr_summary": self._summarize_text(stderr),
                "started_at": started_at,
                "finished_at": finished_at,
            }
        except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
            finished_at = datetime.now(timezone.utc)
            message = str(exc)
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": message,
                "stdout_summary": "",
                "stderr_summary": self._summarize_text(message),
                "started_at": started_at,
                "finished_at": finished_at,
            }

    def _summarize_text(self, text: str, max_len: int = 220) -> str:
        if not text:
            return ""
        cleaned = " ".join(text.split())
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[: max_len - 3] + "..."

    def _parse_task_output(
        self,
        task_name: str,
        raw_outputs: dict[str, str],
    ) -> tuple[Any | None, str, str]:
        if task_name == "collect_system_identity":
            hostname = raw_outputs.get("hostname", "").strip()
            os_version = raw_outputs.get("os_version", "").strip()
            os_name_raw = raw_outputs.get("os_name", "").strip()
            boot_time = raw_outputs.get("boot_time", "")
            uptime_seconds = self._parse_uptime_seconds(boot_time)
            os_name = "macOS" if os_name_raw.lower() in {"darwin", "macos"} else (os_name_raw or "macOS")
            if os_version and not os_version.lower().startswith("macos"):
                os_version = f"macOS {os_version}"
            artifact = {
                "hostname": hostname or "unknown",
                "os_name": os_name or "macOS",
                "os_version": os_version or "macOS unknown",
                "uptime_seconds": uptime_seconds,
            }
            return artifact, "system_identity", f"{artifact['hostname']} / {artifact['os_version']}"

        if task_name == "collect_resource_usage":
            total_mem = self._parse_memsize_mb(raw_outputs.get("memory_total", ""))
            used_mem = self._parse_used_memory_mb(raw_outputs.get("vm_stat", ""), total_mem)
            cpu_percent = self._parse_cpu_percent(raw_outputs.get("cpu_lines", ""))
            artifact = {
                "memory_total_mb": total_mem,
                "memory_used_mb": used_mem,
                "cpu_percent": cpu_percent,
            }
            return (
                artifact,
                "resource_usage",
                f"cpu={cpu_percent:.1f}% memory={used_mem}/{total_mem}MB",
            )

        if task_name == "collect_processes":
            processes = self._parse_processes(raw_outputs.get("process_table", ""))
            return processes, "process_list", f"{len(processes)} process rows parsed"

        if task_name == "collect_open_ports":
            ports = self._parse_ports(raw_outputs)
            return ports, "open_ports", f"{len(ports)} listening ports parsed"

        if task_name == "collect_disk_usage":
            disk = self._parse_disk(raw_outputs.get("disk_df", ""))
            if disk is None:
                return None, "disk_usage", "disk parser failed"
            return disk, "disk_usage", f"{disk['disk_usage_percent']:.1f}% used"

        return None, "unknown", "unsupported task"

    def _parse_uptime_seconds(self, boot_time_output: str) -> int:
        if not boot_time_output:
            return 0
        match = re.search(r"sec = (\d+)", boot_time_output)
        if not match:
            return 0
        try:
            boot_time = int(match.group(1))
        except ValueError:
            return 0
        now = int(datetime.now(timezone.utc).timestamp())
        return max(0, now - boot_time)

    def _parse_memsize_mb(self, memsize_output: str) -> int:
        try:
            return int(int(memsize_output.strip()) / (1024 * 1024))
        except (TypeError, ValueError):
            return 0

    def _parse_used_memory_mb(self, vm_stat_output: str, total_memory_mb: int) -> int:
        if not vm_stat_output or total_memory_mb <= 0:
            return 0
        page_size_match = re.search(r"page size of (\d+) bytes", vm_stat_output)
        page_size = int(page_size_match.group(1)) if page_size_match else 4096
        free = self._extract_vm_pages(vm_stat_output, "Pages free")
        speculative = self._extract_vm_pages(vm_stat_output, "Pages speculative")
        free_mb = int(((free + speculative) * page_size) / (1024 * 1024))
        return max(0, min(total_memory_mb, total_memory_mb - free_mb))

    def _extract_vm_pages(self, vm_output: str, label: str) -> int:
        match = re.search(rf"{re.escape(label)}:\s+(\d+)\.", vm_output)
        if not match:
            return 0
        return int(match.group(1))

    def _parse_cpu_percent(self, cpu_lines: str) -> float:
        if not cpu_lines:
            return 0.0
        total = 0.0
        for line in cpu_lines.splitlines():
            try:
                total += float(line.strip())
            except ValueError:
                continue
        cpu_count = max(1, os.cpu_count() or 1)
        return round(max(0.0, min(100.0, total / cpu_count)), 1)

    def _parse_processes(self, process_output: str) -> list[ProcessInfo]:
        if not process_output:
            return []
        processes: list[ProcessInfo] = []
        for line in process_output.splitlines()[:5]:
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
        mapping = {
            "R": "running",
            "S": "sleeping",
            "I": "idle",
            "T": "stopped",
            "Z": "zombie",
            "U": "waiting",
        }
        return mapping.get((state_text[:1] if state_text else "").upper(), "running")

    def _parse_ports(self, raw_outputs: dict[str, str]) -> list[int]:
        if "lsof_ports" in raw_outputs:
            ports: list[int] = []
            for line in raw_outputs["lsof_ports"].splitlines()[1:]:
                match = re.search(r":(\d+)\s+\(LISTEN\)", line)
                if match:
                    ports.append(int(match.group(1)))
            return sorted(set(ports))[:20]

        if "netstat_ports" in raw_outputs:
            ports = []
            for line in raw_outputs["netstat_ports"].splitlines():
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

        return []

    def _parse_disk(self, df_output: str) -> dict[str, Any] | None:
        lines = [line for line in df_output.splitlines() if line.strip()]
        if len(lines) < 2:
            return None
        parts = lines[1].split()
        if len(parts) < 6:
            return None
        try:
            total_kb = int(parts[1])
            used_kb = int(parts[2])
        except ValueError:
            return None
        total_gb = round(total_kb / (1024 * 1024), 1)
        used_gb = round(used_kb / (1024 * 1024), 1)
        usage_percent = round((used_kb / total_kb) * 100, 1) if total_kb else 0.0
        return {
            "disk_total_gb": total_gb,
            "disk_used_gb": used_gb,
            "disk_usage_percent": usage_percent,
        }

    def _derive_services(self, processes: list[ProcessInfo]) -> list[ServiceInfo]:
        preferred = {"Finder", "WindowServer", "mDNSResponder"}
        services: list[ServiceInfo] = []
        for process in processes:
            if process.name not in preferred:
                continue
            services.append(
                ServiceInfo(
                    name=process.name,
                    status="running",
                    description="Observed from allowlisted runtime process inventory",
                    restart_count=0,
                )
            )
        return services

    def _new_batch_id(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + "-runtime-observation"

    def _new_invocation_id(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + "-runtime-command"

    def is_runtime_available(self) -> bool:
        return py_platform.system() == "Darwin"
