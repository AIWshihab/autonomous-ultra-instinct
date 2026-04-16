from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any

from app.core.history_repository import HistoryRepository
from app.models.schemas import (
    AnomalyContext,
    BaselineComparison,
    BaselineSummary,
    DeviationSignal,
    HostBaseline,
    Issue,
    StateSnapshot,
)


class BaselineService:
    HISTORY_WINDOW = 20
    CPU_DELTA = 15.0
    MEMORY_DELTA_RATIO = 0.15
    MEMORY_DELTA_MB = 300.0
    DISK_DELTA = 5.0
    RISK_DELTA = 10.0
    HEALTH_DELTA = 8.0
    COMMON_FREQUENCY_RATIO = 0.4
    HEALTHY_SERVICE_STATUSES = {"running", "healthy"}
    SUPPORTED_EVENT_TYPES = {"snapshot_event", "plan_event", "execute_event"}

    def __init__(self, repository: HistoryRepository | None = None) -> None:
        self.repository = repository or HistoryRepository()

    def compute_baseline(
        self,
        platform: str,
        mode: str,
        hostname: str | None = None,
        limit: int = HISTORY_WINDOW,
    ) -> HostBaseline:
        rows = self.repository.list_events(limit=limit, platform=platform, mode=mode)
        host_snapshots: list[dict[str, Any]] = []
        fallback_snapshots: list[dict[str, Any]] = []

        for row in rows:
            if row["event_type"] not in self.SUPPORTED_EVENT_TYPES:
                continue
            record = self.repository.get_event(row["event_id"])
            if not record:
                continue
            snapshot = record.get("payload", {}).get("snapshot")
            if not isinstance(snapshot, dict):
                continue
            event_hostname = snapshot.get("system_info", {}).get("hostname")
            if hostname and event_hostname == hostname:
                host_snapshots.append(snapshot)
            else:
                fallback_snapshots.append(snapshot)

        if hostname and not host_snapshots:
            host_snapshots = fallback_snapshots

        return self._build_host_baseline(platform, mode, hostname, host_snapshots)

    def _build_host_baseline(
        self,
        platform: str,
        mode: str,
        hostname: str | None,
        snapshots: list[dict[str, Any]],
    ) -> HostBaseline:
        if not snapshots:
            return HostBaseline(
                platform=platform,
                mode=mode,
                hostname=hostname or "unknown",
            )

        cpu_values: list[float] = []
        memory_values: list[float] = []
        memory_percentages: list[float] = []
        disk_values: list[float] = []
        risk_values: list[float] = []
        health_values: list[float] = []
        service_health_counts: Counter[str] = Counter()
        healthy_service_counts: Counter[str] = Counter()
        process_counts: Counter[str] = Counter()

        for snapshot in snapshots:
            resources = snapshot.get("resources", {})
            cpu_values.append(float(resources.get("cpu_percent", 0.0)))
            memory_used_mb = float(resources.get("memory_used_mb", 0.0))
            memory_values.append(memory_used_mb)
            memory_total_mb = float(resources.get("memory_total_mb", 0.0))
            memory_percentages.append(
                (memory_used_mb / memory_total_mb * 100.0) if memory_total_mb else 0.0
            )
            disk_values.append(float(resources.get("disk_usage_percent", 0.0)))
            risk_values.append(float(snapshot.get("risk_score", 0.0)))
            health_values.append(float(snapshot.get("health_score", 100.0)))

            for service in snapshot.get("services", []):
                name = service.get("name")
                if not name:
                    continue
                service_health_counts[name] += 1
                if service.get("status", "").lower() in self.HEALTHY_SERVICE_STATUSES:
                    healthy_service_counts[name] += 1

            for process in snapshot.get("processes", []):
                name = process.get("name")
                if name:
                    process_counts[name] += 1

        event_count = len(snapshots)
        healthy_service_names = [
            name
            for name, count in healthy_service_counts.items()
            if count / event_count >= self.COMMON_FREQUENCY_RATIO
        ]
        common_process_names = [
            name
            for name, count in process_counts.items()
            if count / event_count >= self.COMMON_FREQUENCY_RATIO
        ]

        return HostBaseline(
            platform=platform,
            mode=mode,
            hostname=hostname or snapshots[0].get("system_info", {}).get("hostname", "unknown"),
            event_count=event_count,
            avg_cpu_percent=mean(cpu_values),
            avg_memory_used_mb=mean(memory_values),
            avg_memory_percent=mean(memory_percentages),
            avg_disk_usage_percent=mean(disk_values),
            avg_risk_score=mean(risk_values),
            avg_health_score=mean(health_values),
            healthy_service_names=sorted(healthy_service_names),
            common_process_names=sorted(common_process_names),
        )

    def compute_deviation_signals(
        self,
        snapshot: StateSnapshot,
        baseline: HostBaseline,
    ) -> list[DeviationSignal]:
        if baseline.event_count == 0:
            return []

        signals: list[DeviationSignal] = []
        current_cpu = snapshot.resources.cpu_percent
        cpu_delta = current_cpu - baseline.avg_cpu_percent
        if cpu_delta > self.CPU_DELTA:
            signals.append(
                DeviationSignal(
                    signal_type="cpu_above_baseline",
                    description=f"CPU usage is {current_cpu:.1f}% versus baseline {baseline.avg_cpu_percent:.1f}%.",
                    severity="high" if cpu_delta >= 25.0 else "medium",
                    current_value=current_cpu,
                    baseline_value=baseline.avg_cpu_percent,
                    delta=round(cpu_delta, 1),
                )
            )

        current_memory = snapshot.resources.memory_used_mb
        memory_delta = current_memory - baseline.avg_memory_used_mb
        memory_threshold = max(baseline.avg_memory_used_mb * self.MEMORY_DELTA_RATIO, self.MEMORY_DELTA_MB)
        if memory_delta > memory_threshold:
            signals.append(
                DeviationSignal(
                    signal_type="memory_above_baseline",
                    description=f"Memory used is {current_memory:.1f} MB versus baseline {baseline.avg_memory_used_mb:.1f} MB.",
                    severity="high" if memory_delta >= memory_threshold * 2 else "medium",
                    current_value=current_memory,
                    baseline_value=baseline.avg_memory_used_mb,
                    delta=round(memory_delta, 1),
                )
            )

        current_disk = snapshot.resources.disk_usage_percent
        disk_delta = current_disk - baseline.avg_disk_usage_percent
        if disk_delta > self.DISK_DELTA:
            signals.append(
                DeviationSignal(
                    signal_type="disk_above_baseline",
                    description=f"Disk usage is {current_disk:.1f}% versus baseline {baseline.avg_disk_usage_percent:.1f}%.",
                    severity="high" if disk_delta >= 12.0 else "medium",
                    current_value=current_disk,
                    baseline_value=baseline.avg_disk_usage_percent,
                    delta=round(disk_delta, 1),
                )
            )

        risk_delta = snapshot.risk_score - baseline.avg_risk_score
        if risk_delta > self.RISK_DELTA:
            signals.append(
                DeviationSignal(
                    signal_type="risk_score_above_baseline",
                    description=f"Risk score is {snapshot.risk_score} versus baseline {baseline.avg_risk_score:.1f}.",
                    severity="medium",
                    current_value=snapshot.risk_score,
                    baseline_value=baseline.avg_risk_score,
                    delta=round(risk_delta, 1),
                )
            )

        health_delta = baseline.avg_health_score - snapshot.health_score
        if health_delta > self.HEALTH_DELTA:
            signals.append(
                DeviationSignal(
                    signal_type="health_score_below_baseline",
                    description=f"Health score is {snapshot.health_score} versus baseline {baseline.avg_health_score:.1f}.",
                    severity="medium",
                    current_value=snapshot.health_score,
                    baseline_value=baseline.avg_health_score,
                    delta=round(health_delta, 1),
                )
            )

        unseen_processes = [
            process.name
            for process in snapshot.processes
            if process.name not in baseline.common_process_names
        ]
        if unseen_processes:
            signals.append(
                DeviationSignal(
                    signal_type="unseen_process",
                    description=f"{unseen_processes[0]} is not commonly observed on this host.",
                    severity="medium" if len(unseen_processes) == 1 else "high",
                    current_value=", ".join(unseen_processes[:3]),
                    baseline_value=", ".join(baseline.common_process_names[:5]) or "none",
                    delta=float(len(unseen_processes)),
                )
            )

        regressed_services = [
            service.name
            for service in snapshot.services
            if service.status.lower() not in self.HEALTHY_SERVICE_STATUSES
            and service.name in baseline.healthy_service_names
        ]
        if regressed_services:
            signals.append(
                DeviationSignal(
                    signal_type="service_health_regression",
                    description=f"{regressed_services[0]} was healthy historically but is now {snapshot.services[[s.name for s in snapshot.services].index(regressed_services[0])].status}.",
                    severity="high" if len(regressed_services) > 1 else "medium",
                    current_value=", ".join(regressed_services[:3]),
                    baseline_value=", ".join(baseline.healthy_service_names[:5]) or "none",
                    delta=float(len(regressed_services)),
                )
            )

        return signals

    def build_baseline_summary(
        self,
        snapshot: StateSnapshot,
        baseline: HostBaseline,
    ) -> BaselineSummary:
        comparisons: list[BaselineComparison] = []
        if baseline.event_count > 0:
            comparisons = [
                BaselineComparison(
                    metric="cpu_percent",
                    current_value=snapshot.resources.cpu_percent,
                    baseline_value=baseline.avg_cpu_percent,
                    delta=round(snapshot.resources.cpu_percent - baseline.avg_cpu_percent, 1),
                    trend="above" if snapshot.resources.cpu_percent >= baseline.avg_cpu_percent else "below",
                ),
                BaselineComparison(
                    metric="memory_used_mb",
                    current_value=snapshot.resources.memory_used_mb,
                    baseline_value=baseline.avg_memory_used_mb,
                    delta=round(snapshot.resources.memory_used_mb - baseline.avg_memory_used_mb, 1),
                    trend="above" if snapshot.resources.memory_used_mb >= baseline.avg_memory_used_mb else "below",
                ),
                BaselineComparison(
                    metric="disk_usage_percent",
                    current_value=snapshot.resources.disk_usage_percent,
                    baseline_value=baseline.avg_disk_usage_percent,
                    delta=round(snapshot.resources.disk_usage_percent - baseline.avg_disk_usage_percent, 1),
                    trend="above" if snapshot.resources.disk_usage_percent >= baseline.avg_disk_usage_percent else "below",
                ),
            ]

        signals = self.compute_deviation_signals(snapshot, baseline)
        anomaly_score = min(1.0, 0.1 * len(signals) + sum(0.1 for signal in signals if signal.severity == "high"))
        return BaselineSummary(
            host_baseline=baseline,
            baseline_comparisons=comparisons,
            deviation_signals=signals,
            anomaly_score=round(anomaly_score, 2),
        )

    def enrich_issues(
        self,
        issues: list[Issue],
        snapshot: StateSnapshot,
        baseline_summary: BaselineSummary,
    ) -> list[Issue]:
        if baseline_summary is None:
            return issues

        enriched: list[Issue] = []
        signals_by_type = {signal.signal_type for signal in baseline_summary.deviation_signals}
        host_baseline = baseline_summary.host_baseline

        for issue in issues:
            reasons: list[str] = []
            baseline_note = []
            bonus_score = 0

            if issue.type == "HIGH_RESOURCE_USAGE":
                if "cpu_above_baseline" in signals_by_type:
                    reasons.append("CPU usage is elevated compared to this host baseline.")
                if "memory_above_baseline" in signals_by_type:
                    reasons.append("Memory usage is elevated compared to this host baseline.")

            if issue.type == "DISK_PRESSURE" and "disk_above_baseline" in signals_by_type:
                reasons.append("Disk pressure is worse than the recent host baseline.")

            if issue.type == "SERVICE_DOWN" and issue.target in host_baseline.healthy_service_names:
                reasons.append(f"{issue.target} was usually healthy on this host and now shows regression.")

            if issue.type == "SUSPICIOUS_PROCESS":
                process_name = self._extract_process_name(issue)
                if process_name and process_name not in host_baseline.common_process_names:
                    reasons.append("This process has not appeared in recent host history.")
                    baseline_note.append("new to this host")

            if "risk_score_above_baseline" in signals_by_type:
                baseline_note.append("risk above normal")
            if "health_score_below_baseline" in signals_by_type:
                baseline_note.append("health drift below normal")

            if reasons or baseline_note:
                if reasons:
                    anomaly_reason = " ".join(reasons)
                else:
                    anomaly_reason = "; ".join(baseline_note)
                deviation_score = min(
                    1.0,
                    0.05 * len(reasons)
                    + 0.05 * len(baseline_note)
                    + baseline_summary.anomaly_score * 0.5,
                )
                confidence = min(1.0, issue.confidence + 0.04 * len(reasons))
                priority_score = min(100, issue.priority_score + 2 * len(reasons))
                enriched.append(
                    issue.model_copy(
                        update={
                            "anomaly_reason": anomaly_reason,
                            "baseline_summary": ", ".join(baseline_note) if baseline_note else anomaly_reason,
                            "deviation_score": round(deviation_score, 2),
                            "confidence": confidence,
                            "priority_score": priority_score,
                            "anomaly_context": AnomalyContext(
                                anomaly_reasons=reasons or baseline_note,
                                baseline_comparisons=baseline_summary.baseline_comparisons,
                                deviation_signals=baseline_summary.deviation_signals,
                            ),
                        }
                    )
                )
            else:
                enriched.append(issue)

        return enriched

    def _extract_process_name(self, issue: Issue) -> str | None:
        if issue.description:
            parts = issue.description.split()
            if parts:
                return parts[0].strip()
        return None
