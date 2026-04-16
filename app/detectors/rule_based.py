import re
from typing import List

from app.core.scoring import ScoringEngine
from app.detectors.base_detector import BaseDetector
from app.models.schemas import Issue, ProcessInfo, ServiceInfo, StateSnapshot


class RuleBasedDetector(BaseDetector):
    suspicious_process_tokens = ("unsigned-sync-agent", "unknown-daemon", "temp-updater")
    high_memory_threshold_mb = 400.0
    unhealthy_service_statuses = {"unhealthy", "stopped", "failed"}
    port_conflict_patterns = (
        re.compile(r"port\s+(\d+).+already in use", re.IGNORECASE),
        re.compile(r"port\s+(\d+).+conflict", re.IGNORECASE),
        re.compile(r"listener conflict.+port\s+(\d+)", re.IGNORECASE),
    )

    def __init__(self, scoring_engine: ScoringEngine | None = None) -> None:
        self.scoring_engine = scoring_engine or ScoringEngine()

    def _build_issue(
        self,
        id: str,
        type: str,
        category: str,
        description: str,
        target: str,
        score: dict,
        evidence: list[str],
        detection_reason: str,
        severity_reason: str,
        confidence_reason: str,
    ) -> Issue:
        return Issue(
            id=id,
            type=type,
            category=category,
            description=description,
            target=target,
            evidence=evidence,
            detection_reason=detection_reason,
            severity_reason=severity_reason,
            confidence_reason=confidence_reason,
            **score,
        )

    def detect(self, snapshot: StateSnapshot) -> List[Issue]:
        issues: List[Issue] = []
        issues.extend(self._detect_disk_pressure(snapshot))
        issues.extend(self._detect_service_down(snapshot.services))
        issues.extend(self._detect_crash_loops(snapshot.services))
        issues.extend(self._detect_high_resource_usage(snapshot.processes))
        issues.extend(self._detect_suspicious_processes(snapshot.processes))
        issues.extend(self._detect_port_conflicts(snapshot.recent_logs))
        return issues

    def _detect_disk_pressure(self, snapshot: StateSnapshot) -> List[Issue]:
        if snapshot.resources.disk_usage_percent < 90.0:
            return []
        score = self.scoring_engine.score_disk_pressure(snapshot.resources.disk_usage_percent)
        evidence = [f"disk usage is {snapshot.resources.disk_usage_percent:.1f}%"]
        return [
            self._build_issue(
                id="disk-pressure-001",
                type="DISK_PRESSURE",
                category="storage",
                description="Disk usage is above the conservative threshold.",
                target="/",
                score=score,
                evidence=evidence,
                detection_reason="Disk usage exceeded the V1 threshold of 90%.",
                severity_reason="Disk usage at or above 95% is classified as critical.",
                confidence_reason="Disk percentage is a direct measured signal.",
            )
        ]

    def _detect_service_down(self, services: List[ServiceInfo]) -> List[Issue]:
        issues: List[Issue] = []
        for index, service in enumerate(services, start=1):
            if service.status.lower() not in self.unhealthy_service_statuses:
                continue
            score = self.scoring_engine.score_service_down(service)
            issues.append(
                self._build_issue(
                    id=f"service-down-{index:03d}",
                    type="SERVICE_DOWN",
                    category="service",
                    description=f"{service.name} is reporting status '{service.status}'.",
                    target=service.name,
                    score=score,
                    evidence=[f"service {service.name} status={service.status}"],
                    detection_reason="A monitored service is not healthy.",
                    severity_reason="Service unavailability is high severity in V1.",
                    confidence_reason="Service status is directly observable.",
                )
            )
        return issues

    def _detect_crash_loops(self, services: List[ServiceInfo]) -> List[Issue]:
        issues: List[Issue] = []
        for index, service in enumerate(services, start=1):
            if service.restart_count < 3:
                continue
            score = self.scoring_engine.score_crash_loop(service)
            issues.append(
                self._build_issue(
                    id=f"crash-loop-{index:03d}",
                    type="CRASH_LOOP",
                    category="service",
                    description=f"{service.name} restarted {service.restart_count} times and may be crash looping.",
                    target=service.name,
                    score=score,
                    evidence=[f"restart_count={service.restart_count}"],
                    detection_reason="A service has restarted frequently and may be crash looping.",
                    severity_reason="Frequent service restarts indicate elevated operational risk.",
                    confidence_reason="Restart count is a directly observable service metric.",
                )
            )
        return issues

    def _detect_high_resource_usage(self, processes: List[ProcessInfo]) -> List[Issue]:
        issues: List[Issue] = []
        for index, process in enumerate(processes, start=1):
            if process.cpu_percent < 80.0 and process.memory_mb < self.high_memory_threshold_mb:
                continue
            score = self.scoring_engine.score_high_resource_usage(process)
            if process.cpu_percent >= 80.0:
                reason = f"CPU {process.cpu_percent:.1f}% exceeded threshold."
                evidence = [f"cpu usage is {process.cpu_percent:.1f}%"]
            else:
                reason = f"Memory {process.memory_mb:.1f} MB exceeded threshold."
                evidence = [f"memory usage is {process.memory_mb:.1f} MB"]
            issues.append(
                self._build_issue(
                    id=f"high-resource-{index:03d}",
                    type="HIGH_RESOURCE_USAGE",
                    category="process",
                    description=f"{process.name} is consuming elevated resources. {reason}",
                    target=f"pid:{process.pid}",
                    score=score,
                    evidence=evidence,
                    detection_reason="Process resource usage exceeded defined V1 thresholds.",
                    severity_reason="Excessive CPU or memory usage is considered elevated severity.",
                    confidence_reason="Resource metrics are directly measurable from the process sample.",
                )
            )
        return issues

    def _detect_suspicious_processes(self, processes: List[ProcessInfo]) -> List[Issue]:
        issues: List[Issue] = []
        for index, process in enumerate(processes, start=1):
            process_name = process.name.lower()
            if not any(token in process_name for token in self.suspicious_process_tokens):
                continue
            score = self.scoring_engine.score_suspicious_process(process)
            issues.append(
                self._build_issue(
                    id=f"suspicious-process-{index:03d}",
                    type="SUSPICIOUS_PROCESS",
                    category="process",
                    description=f"{process.name} matched the conservative suspicious-process rule set.",
                    target=f"pid:{process.pid}",
                    score=score,
                    evidence=[f"process name is {process.name}"],
                    detection_reason="A monitored process name matched the suspicious V1 token list.",
                    severity_reason="Suspicious process markers are classified as high risk in V1.",
                    confidence_reason="Process metadata is directly observable.",
                )
            )
        return issues

    def _detect_port_conflicts(self, recent_logs: List[str]) -> List[Issue]:
        issues: List[Issue] = []
        evidence_by_port: dict[int, int] = {}

        for log_line in recent_logs:
            port = self._extract_port_conflict_port(log_line)
            if port is None:
                continue
            evidence_by_port[port] = evidence_by_port.get(port, 0) + 1

        for index, (port, evidence_count) in enumerate(sorted(evidence_by_port.items()), start=1):
            score = self.scoring_engine.score_port_conflict(evidence_count)
            evidence = [f"log evidence for port {port}: {evidence_count} entries"]
            issues.append(
                self._build_issue(
                    id=f"port-conflict-{index:03d}",
                    type="PORT_CONFLICT",
                    category="network",
                    description=f"Recent logs indicate a conflict for port {port}. Evidence count: {evidence_count}.",
                    target=f"port:{port}",
                    score=score,
                    evidence=evidence,
                    detection_reason="Recent logs include port conflict patterns.",
                    severity_reason="Repeated conflict logs increase severity in V1.",
                    confidence_reason="Log pattern matching is a direct observed signal.",
                )
            )
        return issues

    def _extract_port_conflict_port(self, log_line: str) -> int | None:
        for pattern in self.port_conflict_patterns:
            match = pattern.search(log_line)
            if match:
                return int(match.group(1))
        return None
