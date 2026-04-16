from typing import List

from app.core.playbook_engine import PlaybookEngine
from app.models.schemas import Action, Issue, RemediationStrategy


class Planner:
    """Plan actions based on detected issues."""

    def __init__(self, playbook_engine: PlaybookEngine | None = None) -> None:
        self.playbook_engine = playbook_engine or PlaybookEngine()

    def plan(self, issues: List[Issue]) -> List[Action]:
        actions, _ = self.plan_with_strategies(issues)
        return actions

    def plan_with_strategies(self, issues: List[Issue]) -> tuple[List[Action], List[RemediationStrategy]]:
        actions: List[Action] = []
        strategies: List[RemediationStrategy] = []
        prioritized_issues = sorted(
            issues,
            key=lambda issue: (-issue.priority_score, issue.id),
        )
        for issue in prioritized_issues:
            actions.extend(self._actions_for_issue(issue))
            strategies.append(self.playbook_engine.build_strategy(issue))
        return actions, strategies

    def _actions_for_issue(self, issue: Issue) -> List[Action]:
        issue_target = issue.target or issue.category

        if issue.type == "SERVICE_DOWN":
            return [
                self._build_action(
                    issue=issue,
                    action_type="inspect_process",
                    target=issue_target,
                    description=f"Inspect process indicators for service {issue_target}.",
                    planning_reason="SERVICE_DOWN playbook begins with a safe process inspection step.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="collect_forensic_snapshot",
                    target=issue_target,
                    description=f"Collect service diagnostics and log context for {issue_target}.",
                    planning_reason="SERVICE_DOWN playbook collects forensic evidence before remediation.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="restart_service",
                    target=issue_target,
                    description=f"Restart service {issue_target} after detecting a service-down condition.",
                    planning_reason="SERVICE_DOWN playbook proposes a controlled restart after observation steps.",
                )
            ]

        if issue.type == "CRASH_LOOP":
            return [
                self._build_action(
                    issue=issue,
                    action_type="inspect_process",
                    target=issue_target,
                    description=f"Inspect runtime context for crash-looping service {issue_target}.",
                    planning_reason="CRASH_LOOP issues require process inspection before restart strategy.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="collect_forensic_snapshot",
                    target=issue_target,
                    description=f"Collect crash-loop evidence and restart telemetry for {issue_target}.",
                    planning_reason="CRASH_LOOP issues require evidence capture before remediation.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="restart_service",
                    target=issue_target,
                    description=f"Restart crash-looping service {issue_target} in controlled simulation.",
                    planning_reason="CRASH_LOOP issues may stabilize after a controlled restart simulation.",
                ),
            ]

        if issue.type == "PORT_CONFLICT":
            return [
                self._build_action(
                    issue=issue,
                    action_type="inspect_port_usage",
                    target=issue_target,
                    description=f"Inspect port usage for {issue_target} before making any changes.",
                    planning_reason="PORT_CONFLICT evidence maps to a safe observational port inspection first.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="inspect_process",
                    target=issue_target,
                    description=f"Inspect process metadata associated with {issue_target}.",
                    planning_reason="PORT_CONFLICT strategy identifies process ownership before containment steps.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="collect_forensic_snapshot",
                    target=issue_target,
                    description=f"Collect forensic context for conflict evidence on {issue_target}.",
                    planning_reason="PORT_CONFLICT strategy collects evidence before high-risk actions.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="stop_conflicting_process",
                    target=issue_target,
                    description=f"Stop the conflicting process associated with {issue_target}.",
                    planning_reason="PORT_CONFLICT may lead to a process stop only after safer observation steps.",
                ),
            ]

        if issue.type == "DISK_PRESSURE":
            return [
                self._build_action(
                    issue=issue,
                    action_type="inspect_process",
                    target=issue_target,
                    description=f"Inspect high-impact processes contributing to disk pressure on {issue_target}.",
                    planning_reason="DISK_PRESSURE strategy starts with read-only process inspection.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="collect_forensic_snapshot",
                    target=issue_target,
                    description=f"Collect disk-pressure forensic context for target {issue_target}.",
                    planning_reason="DISK_PRESSURE strategy captures diagnostics before cleanup proposals.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="clear_temp_files",
                    target=issue_target,
                    description=f"Clear temporary files under {issue_target} to relieve disk pressure.",
                    planning_reason="DISK_PRESSURE issues map to temporary cleanup in the V1 planner.",
                )
            ]

        if issue.type == "SUSPICIOUS_PROCESS":
            return [
                self._build_action(
                    issue=issue,
                    action_type="inspect_process",
                    target=issue_target,
                    description=f"Inspect suspicious process details for {issue_target}.",
                    planning_reason="SUSPICIOUS_PROCESS evidence maps to process inspection first.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="collect_forensic_snapshot",
                    target=issue_target,
                    description=f"Collect a forensic snapshot for suspicious process {issue_target}.",
                    planning_reason="SUSPICIOUS_PROCESS evidence maps to forensic snapshot collection in V1.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="quarantine_process",
                    target=issue_target,
                    description=f"Quarantine suspicious process {issue_target}.",
                    planning_reason="SUSPICIOUS_PROCESS may require quarantine after observation steps.",
                ),
            ]

        if issue.type == "HIGH_RESOURCE_USAGE":
            return [
                self._build_action(
                    issue=issue,
                    action_type="inspect_process",
                    target=issue_target,
                    description=f"Inspect high-resource process details for {issue_target}.",
                    planning_reason="HIGH_RESOURCE_USAGE strategy starts with a process inspection step.",
                ),
                self._build_action(
                    issue=issue,
                    action_type="collect_forensic_snapshot",
                    target=issue_target,
                    description=f"Collect a forensic snapshot for resource-heavy workload {issue_target}.",
                    planning_reason="HIGH_RESOURCE_USAGE strategy records evidence for workload analysis.",
                ),
            ]

        return []

    def _build_action(
        self,
        issue: Issue,
        action_type: str,
        target: str,
        description: str,
        planning_reason: str,
    ) -> Action:
        return Action(
            id=f"{issue.id}:{action_type}",
            action_type=action_type,
            issue_id=issue.id,
            target=target,
            description=description,
            planning_reason=planning_reason,
        )
