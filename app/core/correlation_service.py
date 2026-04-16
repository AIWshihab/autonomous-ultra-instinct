from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.core.history_repository import HistoryRepository
from app.models.schemas import HistoryEventSummary, IncidentDetail, IncidentSummary, Issue


class CorrelationService:
    WINDOW_SIZE = 100
    MATCH_TYPES = {"snapshot_event", "plan_event", "execute_event"}

    def __init__(self, repository: HistoryRepository | None = None) -> None:
        self.repository = repository or HistoryRepository()

    def _parse_datetime(self, value: str) -> datetime:
        return datetime.fromisoformat(value)

    def _normalize_target(self, issue: dict[str, Any], event_snapshot: dict[str, Any]) -> str:
        issue_type = issue.get("type", "unknown")
        if issue_type == "DISK_PRESSURE":
            hostname = event_snapshot.get("system_info", {}).get("hostname")
            return hostname or issue.get("target", "disk")

        if issue_type in {"SERVICE_DOWN", "CRASH_LOOP"}:
            return issue.get("target", issue.get("description", "unknown-service"))

        if issue_type in {"HIGH_RESOURCE_USAGE", "SUSPICIOUS_PROCESS"}:
            description = issue.get("description", "")
            match = re.match(r"^([\w\-\.]+)", description)
            if match:
                return match.group(1)
            return issue.get("target", "unknown-process")

        if issue_type == "PORT_CONFLICT":
            return issue.get("target", "unknown-port")

        return issue.get("target", issue.get("description", issue.get("type", "unknown")))

    def _build_incident_key(self, platform: str, issue_type: str, normalized_target: str) -> str:
        return f"{platform}:{issue_type}:{normalized_target}"

    def _build_issue_history(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for event in events:
            payload = event.get("payload") or {}
            snapshot = payload.get("snapshot") or {}
            issues = snapshot.get("issues") or []
            for issue in issues:
                normalized_target = self._normalize_target(issue, snapshot)
                history.append(
                    {
                        "event_id": event["event_id"],
                        "event_type": event["event_type"],
                        "created_at": event["created_at"],
                        "platform": event["platform"],
                        "mode": event["mode"],
                        "issue_type": issue.get("type"),
                        "target": issue.get("target"),
                        "normalized_target": normalized_target,
                        "incident_key": self._build_incident_key(event["platform"], issue.get("type", "unknown"), normalized_target),
                        "severity": issue.get("severity"),
                        "properties": issue,
                        "snapshot": snapshot,
                    }
                )
        return history

    def _recurrence_status(self, prior_count: int) -> str:
        if prior_count == 0:
            return "new"
        if prior_count < 3:
            return "recurring"
        return "chronic"

    def _recommendation_level(self, max_severity: str, recurrence_count: int) -> str:
        if max_severity == "critical" or recurrence_count >= 4:
            return "high"
        if max_severity == "high" or recurrence_count >= 2:
            return "medium"
        return "low"

    def _trend_by_type(
        self,
        issue_type: str,
        current_issue: dict[str, Any],
        prior_matches: list[dict[str, Any]],
    ) -> str:
        if not prior_matches:
            return "unknown"

        if issue_type == "DISK_PRESSURE":
            current_value = self._parse_disk_pressure(current_issue)
            last_value = self._parse_disk_pressure(prior_matches[-1])
            if current_value is None or last_value is None:
                return "unknown"
            if current_value > last_value + 0.5:
                return "worsening"
            if current_value < last_value - 0.5:
                return "improving"
            return "stable"

        if issue_type in {"SERVICE_DOWN", "CRASH_LOOP", "SUSPICIOUS_PROCESS", "PORT_CONFLICT"}:
            return "worsening" if len(prior_matches) >= 2 else "stable"

        return "unknown"

    def _parse_disk_pressure(self, issue_or_record: dict[str, Any]) -> float | None:
        if issue_or_record.get("issue_type") == "DISK_PRESSURE":
            evidence = issue_or_record.get("properties", {}).get("evidence", [])
            if evidence and isinstance(evidence, list):
                match = re.search(r"(\d+\.?\d*)%", evidence[0])
                if match:
                    return float(match.group(1))
        if issue_or_record.get("issue_type") is None and issue_or_record.get("type") == "DISK_PRESSURE":
            evidence = issue_or_record.get("evidence", [])
            if evidence and isinstance(evidence, list):
                match = re.search(r"(\d+\.?\d*)%", evidence[0])
                if match:
                    return float(match.group(1))
        resource = issue_or_record.get("snapshot", {}).get("resources", {})
        disk = resource.get("disk_usage_percent")
        if isinstance(disk, (int, float)):
            return float(disk)
        return None

    def _flatten_history(self, platform: str | None = None, mode: str | None = None, limit: int = WINDOW_SIZE) -> list[dict[str, Any]]:
        rows = self.repository.list_events(limit=limit, offset=0, platform=platform, mode=mode)
        events = [self.repository.get_event(row["event_id"]) for row in rows]
        return [record for record in self._build_issue_history(events) if record["issue_type"]]

    def enrich_issues(self, issues: list[Issue], platform: str, mode: str, event_snapshot: dict[str, Any] | None = None) -> list[Issue]:
        history = self._flatten_history(platform=platform, mode=mode)
        enriched: list[Issue] = []
        event_snapshot = event_snapshot or {}

        for issue in issues:
            normalized_target = self._normalize_target(issue.model_dump(), event_snapshot)
            incident_key = self._build_incident_key(platform, issue.type, normalized_target)
            prior_matches = [entry for entry in history if entry["incident_key"] == incident_key]
            if prior_matches:
                prior_matches = sorted(prior_matches, key=lambda event: event["created_at"])
            recurrence_count = len({entry["event_id"] for entry in prior_matches})
            first_seen_at = self._parse_datetime(prior_matches[0]["created_at"]) if prior_matches else None
            last_seen_at = self._parse_datetime(prior_matches[-1]["created_at"]) if prior_matches else None
            trend_direction = self._trend_by_type(issue.type, issue.model_dump(), prior_matches)
            enriched.append(
                issue.model_copy(
                    update={
                        "recurrence_status": self._recurrence_status(recurrence_count),
                        "recurrence_count": recurrence_count,
                        "first_seen_at": first_seen_at,
                        "last_seen_at": last_seen_at,
                        "related_event_ids": sorted({entry["event_id"] for entry in prior_matches}),
                        "incident_key": incident_key,
                        "trend_direction": trend_direction,
                    }
                )
            )

        return enriched

    def list_incidents(
        self,
        limit: int = 50,
        platform: str | None = None,
        mode: str | None = None,
    ) -> list[IncidentSummary]:
        history = self._flatten_history(platform=platform, mode=mode)
        clusters: dict[str, dict[str, Any]] = {}

        for issue_record in history:
            key = issue_record["incident_key"]
            cluster = clusters.setdefault(
                key,
                {
                    "incident_key": key,
                    "issue_type": issue_record["issue_type"],
                    "target": issue_record["normalized_target"],
                    "platform": issue_record["platform"],
                    "related_event_ids": set(),
                    "severity_values": [],
                    "event_times": [],
                },
            )
            cluster["related_event_ids"].add(issue_record["event_id"])
            severity = issue_record.get("severity")
            if severity:
                cluster["severity_values"].append(severity)
            cluster["event_times"].append(issue_record["created_at"])

        summaries: list[IncidentSummary] = []
        for cluster in clusters.values():
            last_seen = max(cluster["event_times"], key=lambda value: value)
            severity_summary = self._highest_severity(cluster["severity_values"])
            recurrence_count = len(cluster["related_event_ids"])
            trend_direction = "worsening" if recurrence_count >= 2 else "stable"
            summaries.append(
                IncidentSummary(
                    incident_key=cluster["incident_key"],
                    incident_title=f"{cluster['issue_type']} on {cluster['target']}",
                    issue_type=cluster["issue_type"],
                    target=cluster["target"],
                    platform=cluster["platform"],
                    severity_summary=severity_summary,
                    recurrence_count=recurrence_count,
                    last_seen_at=self._parse_datetime(last_seen),
                    related_event_ids=sorted(cluster["related_event_ids"]),
                    recommended_attention_level=self._recommendation_level(severity_summary, recurrence_count),
                    trend_direction=trend_direction,
                )
            )

        return sorted(summaries, key=lambda incident: incident.last_seen_at, reverse=True)[:limit]

    def get_incident(self, incident_key: str) -> IncidentDetail | None:
        history = self._flatten_history()
        records = [entry for entry in history if entry["incident_key"] == incident_key]
        if not records:
            return None

        cluster = {
            "issue_type": records[0]["issue_type"],
            "target": records[0]["normalized_target"],
            "platform": records[0]["platform"],
            "related_event_ids": sorted({entry["event_id"] for entry in records}),
            "severity_values": [entry.get("severity") for entry in records if entry.get("severity")],
            "event_times": [entry["created_at"] for entry in records],
        }
        last_seen = max(cluster["event_times"], key=lambda value: value)
        severity_summary = self._highest_severity(cluster["severity_values"])
        recurrence_count = len(cluster["related_event_ids"])
        trend_direction = "worsening" if recurrence_count >= 2 else "stable"

        return IncidentDetail(
            incident_key=incident_key,
            incident_title=f"{cluster['issue_type']} on {cluster['target']}",
            issue_type=cluster["issue_type"],
            target=cluster["target"],
            platform=cluster["platform"],
            severity_summary=severity_summary,
            recurrence_count=recurrence_count,
            last_seen_at=self._parse_datetime(last_seen),
            related_event_ids=cluster["related_event_ids"],
            recommended_attention_level=self._recommendation_level(severity_summary, recurrence_count),
            trend_direction=trend_direction,
            related_events=[
                HistoryEventSummary(
                    event_id=entry["event_id"],
                    event_type=entry.get("event_type", "unknown"),
                    platform=entry["platform"],
                    mode=entry.get("mode", "unknown"),
                    created_at=self._parse_datetime(entry["created_at"]),
                    health_score=0,
                    risk_score=0,
                    issue_count=0,
                )
                for entry in records
            ],
        )

    def _highest_severity(self, severities: list[str]) -> str:
        order = ["critical", "high", "medium", "low"]
        for level in order:
            if level in severities:
                return level
        return "low"
