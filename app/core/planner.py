from typing import List

from app.core.playbook_engine import PlaybookEngine
from app.core.strategy_engine import StrategyEngine
from app.models.schemas import Action, Issue, RemediationStrategy, StrategySelection


class Planner:
    """Plan actions based on detected issues."""
    BLOCKED_PREVIEW_ACTION_TYPES = {
        "stop_conflicting_process",
        "clear_temp_files",
        "quarantine_process",
    }

    def __init__(
        self,
        playbook_engine: PlaybookEngine | None = None,
        strategy_engine: StrategyEngine | None = None,
    ) -> None:
        self.playbook_engine = playbook_engine or PlaybookEngine()
        self.strategy_engine = strategy_engine or StrategyEngine()

    def plan(self, issues: List[Issue]) -> List[Action]:
        actions, _, _ = self.plan_with_strategy_selection(issues)
        return actions

    def plan_with_strategies(
        self,
        issues: List[Issue],
        *,
        platform: str = "linux",
        mode: str = "mock",
    ) -> tuple[List[Action], List[RemediationStrategy]]:
        actions, strategies, _ = self.plan_with_strategy_selection(
            issues,
            platform=platform,
            mode=mode,
        )
        return actions, strategies

    def plan_with_strategy_selection(
        self,
        issues: List[Issue],
        *,
        platform: str = "linux",
        mode: str = "mock",
    ) -> tuple[List[Action], List[RemediationStrategy], List[StrategySelection]]:
        actions: List[Action] = []
        strategies: List[RemediationStrategy] = []
        selections: List[StrategySelection] = []
        prioritized_issues = sorted(
            issues,
            key=lambda issue: (-issue.priority_score, issue.id),
        )
        for issue in prioritized_issues:
            selection = self.strategy_engine.select_for_issue(
                issue,
                platform=platform,
                mode=mode,
            )
            selections.append(selection)
            selected_actions = selection.selected_strategy.action_types
            added_action_types = set(selected_actions)
            actions.extend(
                self._actions_for_issue(
                    issue,
                    selected_action_types=selected_actions,
                    strategy_name=selection.selected_strategy.name,
                )
            )
            blocked_preview_action_types = [
                action_type
                for ranked_candidate in selection.ranked_candidates[1:]
                for action_type in ranked_candidate.strategy.action_types
                if action_type in self.BLOCKED_PREVIEW_ACTION_TYPES and action_type not in added_action_types
            ]
            if blocked_preview_action_types:
                actions.extend(
                    self._actions_for_issue(
                        issue,
                        selected_action_types=blocked_preview_action_types,
                        strategy_name="lower-ranked blocked alternative preview",
                    )
                )
                added_action_types.update(blocked_preview_action_types)
            strategies.append(
                self.playbook_engine.build_strategy(
                    issue,
                    selected_strategy=selection.selected_strategy,
                )
            )
        return actions, strategies, selections

    def _actions_for_issue(
        self,
        issue: Issue,
        *,
        selected_action_types: list[str] | None = None,
        strategy_name: str | None = None,
    ) -> List[Action]:
        issue_target = issue.target or issue.category
        action_types = selected_action_types or self._default_action_types(issue.type)
        blueprint = self._action_blueprints_for_issue(issue)

        resolved_actions = []
        for action_type in action_types:
            if action_type not in blueprint:
                continue
            description_template, reason_template = blueprint[action_type]
            strategy_hint = f" Selected strategy: {strategy_name}." if strategy_name else ""
            resolved_actions.append(
                self._build_action(
                    issue=issue,
                    action_type=action_type,
                    target=issue_target,
                    description=description_template.format(target=issue_target),
                    planning_reason=f"{reason_template}{strategy_hint}",
                )
            )
        return resolved_actions

    def _default_action_types(self, issue_type: str) -> list[str]:
        defaults: dict[str, list[str]] = {
            "SERVICE_DOWN": ["inspect_process", "collect_forensic_snapshot", "restart_service"],
            "CRASH_LOOP": ["inspect_process", "collect_forensic_snapshot", "restart_service"],
            "PORT_CONFLICT": ["inspect_port_usage", "inspect_process", "collect_forensic_snapshot", "stop_conflicting_process"],
            "DISK_PRESSURE": ["inspect_process", "collect_forensic_snapshot", "clear_temp_files"],
            "SUSPICIOUS_PROCESS": ["inspect_process", "collect_forensic_snapshot", "quarantine_process"],
            "HIGH_RESOURCE_USAGE": ["inspect_process", "collect_forensic_snapshot"],
        }
        return defaults.get(issue_type, [])

    def _action_blueprints_for_issue(self, issue: Issue) -> dict[str, tuple[str, str]]:
        issue_type = issue.type
        if issue_type == "SERVICE_DOWN":
            return {
                "inspect_process": (
                    "Inspect process indicators for service {target}.",
                    "SERVICE_DOWN strategy begins with safe process inspection.",
                ),
                "collect_forensic_snapshot": (
                    "Collect service diagnostics and log context for {target}.",
                    "SERVICE_DOWN strategy emphasizes evidence before disruptive actions.",
                ),
                "inspect_port_usage": (
                    "Refresh runtime listener view for {target}.",
                    "SERVICE_DOWN alternate strategy uses runtime refresh to increase confidence.",
                ),
                "restart_service": (
                    "Restart service {target} after controlled observation steps.",
                    "SERVICE_DOWN strategy proposes controlled restart when supported.",
                ),
            }
        if issue_type == "CRASH_LOOP":
            return {
                "inspect_process": (
                    "Inspect runtime context for crash-looping service {target}.",
                    "CRASH_LOOP strategy starts with process inspection.",
                ),
                "collect_forensic_snapshot": (
                    "Collect crash-loop evidence and restart telemetry for {target}.",
                    "CRASH_LOOP strategy captures evidence before recovery attempts.",
                ),
                "restart_service": (
                    "Restart crash-looping service {target} in controlled simulation.",
                    "CRASH_LOOP strategy may propose restart after evidence collection.",
                ),
            }
        if issue_type == "PORT_CONFLICT":
            return {
                "inspect_port_usage": (
                    "Inspect port usage for {target} before any change.",
                    "PORT_CONFLICT strategy uses read-only inspection first.",
                ),
                "inspect_process": (
                    "Inspect process metadata associated with {target}.",
                    "PORT_CONFLICT strategy identifies process ownership before escalation.",
                ),
                "collect_forensic_snapshot": (
                    "Collect forensic context for conflict evidence on {target}.",
                    "PORT_CONFLICT strategy captures evidence for operator review.",
                ),
                "stop_conflicting_process": (
                    "Propose stopping conflicting process associated with {target}.",
                    "PORT_CONFLICT aggressive branch includes stop proposal for governance review.",
                ),
            }
        if issue_type == "DISK_PRESSURE":
            return {
                "inspect_process": (
                    "Inspect high-impact processes contributing to disk pressure on {target}.",
                    "DISK_PRESSURE strategy starts with safe inspection.",
                ),
                "collect_forensic_snapshot": (
                    "Collect disk-pressure forensic context for target {target}.",
                    "DISK_PRESSURE strategy gathers evidence before cleanup consideration.",
                ),
                "clear_temp_files": (
                    "Propose clearing temporary files under {target}.",
                    "DISK_PRESSURE cleanup branch is policy-gated and approval-heavy.",
                ),
            }
        if issue_type == "SUSPICIOUS_PROCESS":
            return {
                "inspect_process": (
                    "Inspect suspicious process details for {target}.",
                    "SUSPICIOUS_PROCESS strategy starts with process inspection.",
                ),
                "collect_forensic_snapshot": (
                    "Collect a forensic snapshot for suspicious process {target}.",
                    "SUSPICIOUS_PROCESS strategy captures forensic evidence early.",
                ),
                "quarantine_process": (
                    "Propose quarantining suspicious process {target}.",
                    "SUSPICIOUS_PROCESS containment branch is high-risk and approval-gated.",
                ),
            }
        if issue_type == "HIGH_RESOURCE_USAGE":
            return {
                "inspect_process": (
                    "Inspect high-resource process details for {target}.",
                    "HIGH_RESOURCE_USAGE strategy focuses on inspection before intervention.",
                ),
                "collect_forensic_snapshot": (
                    "Collect forensic context for resource-heavy workload {target}.",
                    "HIGH_RESOURCE_USAGE strategy captures evidence for controlled follow-up.",
                ),
            }
        return {
            "inspect_process": (
                "Inspect process context for {target}.",
                "Default strategy performs safe process inspection.",
            ),
            "collect_forensic_snapshot": (
                "Collect forensic context for {target}.",
                "Default strategy gathers evidence first.",
            ),
        }

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
