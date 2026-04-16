from app.core.policy_engine import PolicyEngine
from app.models.schemas import Action


def test_policy_engine_classifies_observe_actions():
    engine = PolicyEngine()
    action = Action(
        id="issue-1:inspect_process",
        action_type="inspect_process",
        issue_id="issue-1",
        target="pid:4888",
        description="Inspect suspicious process",
    )

    evaluated_action = engine.evaluate_actions([action])[0]

    assert evaluated_action.allowed is True
    assert evaluated_action.risk_tier == "observe"
    assert evaluated_action.action_confidence == 0.95
    assert evaluated_action.approval_required is False
    assert evaluated_action.execution_mode == "observe_only"
    assert evaluated_action.policy_reason


def test_policy_engine_classifies_collect_forensic_snapshot():
    engine = PolicyEngine()
    action = Action(
        id="issue-1:collect_forensic_snapshot",
        action_type="collect_forensic_snapshot",
        issue_id="issue-1",
        target="pid:4888",
        description="Collect forensic data",
    )

    evaluated_action = engine.evaluate_actions([action])[0]

    assert evaluated_action.allowed is True
    assert evaluated_action.risk_tier == "low"
    assert evaluated_action.approval_required is False
    assert evaluated_action.execution_mode == "simulate_only"


def test_restart_service_requires_approval_in_live_mode():
    engine = PolicyEngine()
    action = Action(
        id="issue-1:restart_service",
        action_type="restart_service",
        issue_id="issue-1",
        target="cache",
        description="Restart cache service",
    )

    mock_action = engine.evaluate_actions([action], mode="mock")[0]
    live_action = engine.evaluate_actions([action], mode="live")[0]

    assert mock_action.allowed is True
    assert mock_action.approval_required is False
    assert mock_action.execution_mode == "simulate_only"
    assert live_action.allowed is True
    assert live_action.approval_required is True
    assert live_action.execution_mode == "simulate_only"


def test_policy_engine_blocks_high_risk_actions():
    engine = PolicyEngine()
    actions = [
        Action(
            id="issue-1:stop_conflicting_process",
            action_type="stop_conflicting_process",
            issue_id="issue-1",
            target="port:8080",
            description="Stop conflicting process",
        ),
        Action(
            id="issue-2:clear_temp_files",
            action_type="clear_temp_files",
            issue_id="issue-2",
            target="/tmp",
            description="Clear temp files",
        ),
        Action(
            id="issue-3:quarantine_process",
            action_type="quarantine_process",
            issue_id="issue-3",
            target="pid:999",
            description="Quarantine process",
        ),
    ]

    evaluated_actions = engine.evaluate_actions(actions)

    assert all(action.allowed is False for action in evaluated_actions)
    assert all(action.execution_mode == "blocked" for action in evaluated_actions)
    assert all(action.approval_required is True for action in evaluated_actions)
    assert all(action.policy_reason for action in evaluated_actions)


def test_policy_engine_returns_policy_subsets():
    engine = PolicyEngine()
    actions = [
        Action(id="a1", action_type="inspect_port_usage", description="inspect"),
        Action(id="a2", action_type="restart_service", description="restart"),
        Action(id="a3", action_type="quarantine_process", description="block"),
    ]

    evaluated_actions = engine.evaluate_actions(actions, mode="live")

    assert len(engine.allowed_actions(evaluated_actions)) == 2
    assert len(engine.approval_required_actions(evaluated_actions)) == 2
    assert len(engine.blocked_actions(evaluated_actions)) == 1
