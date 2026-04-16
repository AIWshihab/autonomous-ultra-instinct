from __future__ import annotations

from app.models.schemas import (
    Action,
    ApprovalPolicy,
    EscalationClass,
    PlaybookStep,
)


class ApprovalPolicyEngine:
    """Deterministic approval policy for human-governed remediation boundaries."""

    def evaluate(
        self,
        *,
        action: Action,
        platform: str,
        mode: str,
        step: PlaybookStep | None = None,
    ) -> ApprovalPolicy:
        del platform
        step_status = (step.status if step is not None else "").lower()
        execution_mode = (action.execution_mode or "").lower()
        risk_tier = (action.risk_tier or "").lower()

        if execution_mode == "blocked" or action.allowed is not True:
            return ApprovalPolicy(
                approval_required=False,
                approval_reason="Action is blocked by policy and is not escalatable in V1.",
                escalation_class=EscalationClass.blocked_non_escalatable,
            )

        if step_status == "approval_pending":
            return ApprovalPolicy(
                approval_required=True,
                approval_reason="Playbook step is explicitly marked as approval_pending.",
                escalation_class=EscalationClass.human_required,
            )

        if mode == "live" and action.action_type == "restart_service":
            return ApprovalPolicy(
                approval_required=True,
                approval_reason="restart_service in live mode requires explicit operator approval.",
                escalation_class=EscalationClass.human_required,
            )

        if mode == "live" and risk_tier in {"medium", "high"}:
            return ApprovalPolicy(
                approval_required=True,
                approval_reason="Live mode medium/high risk remediation requires human approval.",
                escalation_class=EscalationClass.human_required,
            )

        if action.approval_required is True:
            return ApprovalPolicy(
                approval_required=True,
                approval_reason="Action policy metadata requires explicit approval.",
                escalation_class=EscalationClass.human_required,
            )

        if execution_mode == "observe_only" and risk_tier in {"observe", "low"}:
            return ApprovalPolicy(
                approval_required=False,
                approval_reason="Read-only observational step is allowed without approval.",
                escalation_class=EscalationClass.none,
            )

        if mode == "mock" and execution_mode == "simulate_only" and risk_tier in {"observe", "low", "medium"}:
            return ApprovalPolicy(
                approval_required=False,
                approval_reason="Mock-mode simulation step can progress autonomously.",
                escalation_class=EscalationClass.none,
            )

        return ApprovalPolicy(
            approval_required=False,
            approval_reason="No additional approval gate required by deterministic policy.",
            escalation_class=EscalationClass.none,
        )
