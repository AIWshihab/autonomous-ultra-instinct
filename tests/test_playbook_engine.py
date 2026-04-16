import pytest

from app.core.playbook_engine import IncidentStateMachine, InvalidStateTransitionError, PlaybookEngine
from app.models.schemas import (
    Action,
    IncidentLifecycleState,
    Issue,
    VerificationResult,
)


def build_issue(issue_type: str, issue_id: str = "issue-1") -> Issue:
    return Issue(
        id=issue_id,
        type=issue_type,
        category="test",
        description=f"{issue_type} detected",
        target="target-1",
        severity="high",
        confidence=0.9,
        priority_score=80,
    )


def test_valid_incident_state_transition():
    machine = IncidentStateMachine()

    transition = machine.transition(
        current_state=IncidentLifecycleState.detected,
        to_state=IncidentLifecycleState.analyzed,
        reason="analysis complete",
        step_id="analysis",
    )

    assert transition.from_state == IncidentLifecycleState.detected
    assert transition.to_state == IncidentLifecycleState.analyzed


def test_invalid_incident_state_transition_is_blocked():
    machine = IncidentStateMachine()

    with pytest.raises(InvalidStateTransitionError):
        machine.transition(
            current_state=IncidentLifecycleState.detected,
            to_state=IncidentLifecycleState.executed,
            reason="skip all stages",
            step_id="bad-transition",
        )


@pytest.mark.parametrize(
    ("issue_type", "expected_playbook"),
    [
        ("SERVICE_DOWN", "service-down-v1"),
        ("PORT_CONFLICT", "port-conflict-v1"),
        ("DISK_PRESSURE", "disk-pressure-v1"),
        ("SUSPICIOUS_PROCESS", "suspicious-process-v1"),
        ("HIGH_RESOURCE_USAGE", "high-resource-v1"),
    ],
)
def test_playbook_selection_by_issue_type(issue_type: str, expected_playbook: str):
    engine = PlaybookEngine()
    strategy = engine.build_strategy(build_issue(issue_type))

    assert strategy.playbook.playbook_id == expected_playbook


def test_verification_checkpoint_behavior_for_successful_simulation():
    engine = PlaybookEngine()
    issue = build_issue("SERVICE_DOWN")
    strategy = engine.build_strategy(issue)
    actions = [
        Action(
            id="issue-1:inspect_process",
            issue_id="issue-1",
            action_type="inspect_process",
            target="service:nginx",
            description="inspect",
            allowed=True,
            execution_mode="observe_only",
            approval_required=False,
            risk_tier="observe",
            policy_reason="allowed",
        ),
        Action(
            id="issue-1:collect_forensic_snapshot",
            issue_id="issue-1",
            action_type="collect_forensic_snapshot",
            target="service:nginx",
            description="collect",
            allowed=True,
            execution_mode="simulate_only",
            approval_required=False,
            risk_tier="low",
            policy_reason="allowed",
        ),
        Action(
            id="issue-1:restart_service",
            issue_id="issue-1",
            action_type="restart_service",
            target="service:nginx",
            description="restart",
            allowed=True,
            execution_mode="simulate_only",
            approval_required=False,
            risk_tier="medium",
            policy_reason="allowed",
        ),
    ]
    planned_strategies, _ = engine.apply_policy_classification([strategy], actions)
    verification_results = [
        VerificationResult(
            action_id=action.id,
            issue_id=action.issue_id,
            action_type=action.action_type,
            verified=True,
            reason="simulated success",
        )
        for action in actions
    ]

    incident_states, executions, _ = engine.simulate_execution(
        planned_strategies,
        actions,
        verification_results,
    )

    assert incident_states[0].current_state == IncidentLifecycleState.closed
    assert executions[0].verification_checkpoints
    assert all(
        checkpoint.verified is not False for checkpoint in executions[0].verification_checkpoints
    )
