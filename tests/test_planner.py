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

    assert len(actions) == 2
    assert {action.action_type for action in actions} == {
        "inspect_port_usage",
        "stop_conflicting_process",
    }
    assert all(action.issue_id == "issue-2" for action in actions)
    assert all(action.target == "port:5432" for action in actions)
    assert any(
        action.planning_reason == "PORT_CONFLICT evidence maps to a safe observational port inspection first."
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
