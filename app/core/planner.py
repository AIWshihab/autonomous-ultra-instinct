from typing import List

from app.models.schemas import Action, Issue


class Planner:
    """Plan actions based on detected issues."""

    def plan(self, issues: List[Issue]) -> List[Action]:
        actions: List[Action] = []
        prioritized_issues = sorted(
            issues,
            key=lambda issue: (-issue.priority_score, issue.id),
        )
        for issue in prioritized_issues:
            actions.extend(self._actions_for_issue(issue))
        return actions

    def _actions_for_issue(self, issue: Issue) -> List[Action]:
        issue_target = issue.target or issue.category

        if issue.type == "SERVICE_DOWN":
            return [
                self._build_action(
                    issue=issue,
                    action_type="restart_service",
                    target=issue_target,
                    description=f"Restart service {issue_target} after detecting a service-down condition.",
                    planning_reason="SERVICE_DOWN issues map to restart_service in the V1 planner.",
                )
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
