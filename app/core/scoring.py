from app.models.schemas import Issue, IssueSummary, ProcessInfo, ServiceInfo


class ScoringEngine:
    severity_base_scores = {
        "critical": 90,
        "high": 70,
        "medium": 45,
        "low": 20,
    }
    risk_weights = {
        "critical": 32,
        "high": 20,
        "medium": 12,
        "low": 6,
    }
    stronger_suspicious_processes = {"unsigned-sync-agent", "unknown-daemon"}

    def score_disk_pressure(self, disk_usage_percent: float) -> dict[str, int | float | str]:
        severity = "critical" if disk_usage_percent >= 95.0 else "high"
        confidence = 0.98 if severity == "critical" else 0.94
        return self._score_payload(severity=severity, confidence=confidence)

    def score_service_down(self, service: ServiceInfo) -> dict[str, int | float | str]:
        del service
        return self._score_payload(severity="high", confidence=0.96)

    def score_crash_loop(self, service: ServiceInfo) -> dict[str, int | float | str]:
        confidence = 0.88 if service.restart_count >= 4 else 0.85
        return self._score_payload(severity="high", confidence=confidence)

    def score_high_resource_usage(self, process: ProcessInfo) -> dict[str, int | float | str]:
        severity = "high" if process.cpu_percent >= 95.0 else "medium"
        confidence = 0.95 if process.cpu_percent >= 95.0 else 0.9
        if process.memory_mb >= 700.0:
            confidence = max(confidence, 0.92)
        return self._score_payload(severity=severity, confidence=confidence)

    def score_suspicious_process(self, process: ProcessInfo) -> dict[str, int | float | str]:
        normalized_name = process.name.lower()
        severity = "high" if normalized_name in self.stronger_suspicious_processes else "medium"
        confidence = 0.68 if severity == "high" else 0.52
        return self._score_payload(severity=severity, confidence=confidence)

    def score_port_conflict(self, evidence_count: int) -> dict[str, int | float | str]:
        severity = "high" if evidence_count >= 2 else "medium"
        confidence = 0.89 if evidence_count >= 2 else 0.8
        return self._score_payload(severity=severity, confidence=confidence)

    def summarize_issues(self, issues: list[Issue]) -> tuple[int, int, IssueSummary]:
        summary = IssueSummary(
            critical_count=sum(1 for issue in issues if issue.severity == "critical"),
            high_count=sum(1 for issue in issues if issue.severity == "high"),
            medium_count=sum(1 for issue in issues if issue.severity == "medium"),
            low_count=sum(1 for issue in issues if issue.severity == "low"),
            total_count=len(issues),
        )

        risk_score = 0.0
        for issue in issues:
            risk_score += self.risk_weights.get(issue.severity, 0) * issue.confidence

        clamped_risk_score = max(0, min(100, round(risk_score)))
        health_score = max(0, min(100, 100 - clamped_risk_score))
        return health_score, clamped_risk_score, summary

    def _score_payload(self, *, severity: str, confidence: float) -> dict[str, int | float | str]:
        priority_score = min(100, self.severity_base_scores[severity] + round(confidence * 10))
        return {
            "severity": severity,
            "confidence": confidence,
            "priority_score": priority_score,
        }
