from app.core.planner import Planner
from app.models.schemas import Issue


def test_planner_creates_actions_for_issues():
    planner = Planner()
    issues = [
        Issue(
            id="issue-2",
            type="PORT_CONFLICT",
            category="network",
            description="Mock issue",
            target="port:5432",
        )
    ]

    actions = planner.plan(issues)

    assert len(actions) >= 2
    assert "inspect_port_usage" in {action.action_type for action in actions}
    assert {action.action_type for action in actions}.issubset({
        "inspect_port_usage",
        "inspect_process",
        "collect_forensic_snapshot",
        "stop_conflicting_process",
    })
    assert all(action.issue_id == "issue-2" for action in actions)
    assert all(action.target == "port:5432" for action in actions)
    assert any(
        "PORT_CONFLICT strategy uses read-only inspection first." in action.planning_reason
        for action in actions
    )


def test_planner_prioritizes_higher_priority_issues_first():
    planner = Planner()
    issues = [
        Issue(
            id="issue-low",
            type="SERVICE_DOWN",
            category="service",
            description="Lower priority service issue",
            target="cache",
            priority_score=50,
        ),
        Issue(
            id="issue-high",
            type="SUSPICIOUS_PROCESS",
            category="process",
            description="Higher priority suspicious process",
            target="pid:999",
            priority_score=80,
        ),
    ]

    actions = planner.plan(issues)

    assert actions[0].issue_id == "issue-high"


def test_planner_builds_remediation_strategy_for_issue():
    planner = Planner()
    issues = [
        Issue(
            id="issue-service",
            type="SERVICE_DOWN",
            category="service",
            description="service unavailable",
            target="nginx",
            priority_score=90,
        )
    ]

    actions, strategies, selections = planner.plan_with_strategy_selection(issues)

    assert actions
    assert len(strategies) == 1
    assert len(selections) == 1
    strategy = strategies[0]
    selection = selections[0]
    assert strategy.issue_type == "SERVICE_DOWN"
    assert strategy.playbook.playbook_id == "service-down-v1"
    assert strategy.selection_reason
    assert strategy.playbook.steps
    assert selection.selected_strategy_id
    assert selection.winning_reason
    assert selection.rejected_reasons
