from app.core.approval_policy import ApprovalPolicyEngine
from app.models.schemas import Action, EscalationClass, PlaybookStep


def test_restart_service_live_requires_approval():
    engine = ApprovalPolicyEngine()
    action = Action(
        id="a1",
        action_type="restart_service",
        description="restart",
        allowed=True,
        risk_tier="medium",
        execution_mode="simulate_only",
    )
    step = PlaybookStep(
        step_id="s1",
        name="Restart",
        description="restart",
        action_type="restart_service",
        success_condition="ok",
        failure_condition="fail",
        status="ready",
    )

    policy = engine.evaluate(action=action, platform="linux", mode="live", step=step)
    assert policy.approval_required is True
    assert policy.escalation_class == EscalationClass.human_required


def test_observe_only_low_risk_does_not_require_approval():
    engine = ApprovalPolicyEngine()
    action = Action(
        id="a2",
        action_type="inspect_process",
        description="inspect",
        allowed=True,
        risk_tier="observe",
        execution_mode="observe_only",
    )
    step = PlaybookStep(
        step_id="s2",
        name="Inspect",
        description="inspect",
        action_type="inspect_process",
        success_condition="ok",
        failure_condition="fail",
        status="ready",
    )

    policy = engine.evaluate(action=action, platform="linux", mode="mock", step=step)
    assert policy.approval_required is False
    assert policy.escalation_class == EscalationClass.none


def test_blocked_action_remains_non_escalatable():
    engine = ApprovalPolicyEngine()
    action = Action(
        id="a3",
        action_type="quarantine_process",
        description="block",
        allowed=False,
        risk_tier="high",
        execution_mode="blocked",
    )
    step = PlaybookStep(
        step_id="s3",
        name="Quarantine",
        description="block",
        action_type="quarantine_process",
        success_condition="ok",
        failure_condition="fail",
        status="blocked",
    )

    policy = engine.evaluate(action=action, platform="linux", mode="live", step=step)
    assert policy.approval_required is False
    assert policy.escalation_class == EscalationClass.blocked_non_escalatable
