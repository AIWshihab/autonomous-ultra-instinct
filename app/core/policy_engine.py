from typing import List

from app.models.schemas import Action


class PolicyEngine:
    """Apply deterministic safety policy metadata to candidate actions."""

    def evaluate_actions(
        self,
        actions: List[Action],
        *,
        platform: str = "linux",
        mode: str = "mock",
    ) -> List[Action]:
        return [
            self._classify_action(action, platform=platform, mode=mode)
            for action in actions
        ]

    def allowed_actions(self, actions: List[Action]) -> List[Action]:
        return [action for action in actions if action.allowed is True]

    def approval_required_actions(self, actions: List[Action]) -> List[Action]:
        return [action for action in actions if action.approval_required is True]

    def blocked_actions(self, actions: List[Action]) -> List[Action]:
        return [
            action
            for action in actions
            if action.allowed is not True or action.execution_mode == "blocked"
        ]

    def dispatchable_actions(self, actions: List[Action]) -> List[Action]:
        return [
            action
            for action in actions
            if action.allowed is True and action.execution_mode != "blocked"
        ]

    def _classify_action(self, action: Action, *, platform: str, mode: str) -> Action:
        if action.action_type == "inspect_port_usage":
            return self._enrich_action(
                action,
                allowed=True,
                risk_tier="observe",
                action_confidence=0.95,
                approval_required=False,
                execution_mode="observe_only",
                policy_reason=f"Approved as a read-only network inspection step on {platform}.",
            )

        if action.action_type == "inspect_process":
            return self._enrich_action(
                action,
                allowed=True,
                risk_tier="observe",
                action_confidence=0.95,
                approval_required=False,
                execution_mode="observe_only",
                policy_reason=f"Approved as a read-only process inspection step on {platform}.",
            )

        if action.action_type == "collect_forensic_snapshot":
            return self._enrich_action(
                action,
                allowed=True,
                risk_tier="low",
                action_confidence=0.9,
                approval_required=False,
                execution_mode="simulate_only",
                policy_reason=f"Approved as low-risk forensic collection on {platform}, limited to simulation.",
            )

        if action.action_type == "restart_service":
            approval_required = mode == "live"
            policy_reason = (
                f"Approved for simulation on {platform}. Live mode requires operator approval before any real restart."
                if approval_required
                else f"Approved for simulation in mock mode on {platform} as a bounded remediation candidate."
            )
            return self._enrich_action(
                action,
                allowed=True,
                risk_tier="medium",
                action_confidence=0.85,
                approval_required=approval_required,
                execution_mode="simulate_only",
                policy_reason=policy_reason,
            )

        if action.action_type == "stop_conflicting_process":
            return self._enrich_action(
                action,
                allowed=False,
                risk_tier="high",
                action_confidence=0.6,
                approval_required=True,
                execution_mode="blocked",
                policy_reason="Blocked because process termination is considered high risk and not enabled.",
            )

        if action.action_type == "clear_temp_files":
            return self._enrich_action(
                action,
                allowed=False,
                risk_tier="medium",
                action_confidence=0.6,
                approval_required=True,
                execution_mode="blocked",
                policy_reason="Blocked because file deletion is not permitted by the current safety policy.",
            )

        if action.action_type == "quarantine_process":
            return self._enrich_action(
                action,
                allowed=False,
                risk_tier="high",
                action_confidence=0.5,
                approval_required=True,
                execution_mode="blocked",
                policy_reason="Blocked because containment actions require human approval and real enforcement is disabled.",
            )

        return self._enrich_action(
            action,
            allowed=False,
            risk_tier="blocked",
            action_confidence=0.2,
            approval_required=True,
            execution_mode="blocked",
            policy_reason="Blocked because the action type is not recognized by the current safety policy.",
        )

    def _enrich_action(
        self,
        action: Action,
        *,
        allowed: bool,
        risk_tier: str,
        action_confidence: float,
        approval_required: bool,
        execution_mode: str,
        policy_reason: str,
    ) -> Action:
        return action.model_copy(
            update={
                "allowed": allowed,
                "risk_tier": risk_tier,
                "action_confidence": action_confidence,
                "approval_required": approval_required,
                "execution_mode": execution_mode,
                "policy_reason": policy_reason,
                "reason": policy_reason,
            }
        )
