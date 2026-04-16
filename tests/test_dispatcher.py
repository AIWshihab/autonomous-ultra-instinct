from app.core.dispatcher import Dispatcher
from app.models.schemas import Action


def test_denied_actions_are_never_executed():
    dispatcher = Dispatcher()
    actions = [
        Action(
            id="issue-1:restart_service",
            action_type="restart_service",
            issue_id="issue-1",
            target="cache",
            description="Restart cache service",
            allowed=True,
            execution_mode="simulate_only",
        ),
        Action(
            id="issue-2:clear_temp_files",
            action_type="clear_temp_files",
            issue_id="issue-2",
            target="/tmp",
            description="Clear temp files",
            allowed=False,
        ),
    ]

    dispatch_result = dispatcher.dispatch(actions)

    assert len(dispatch_result.executed_actions) == 1
    assert dispatch_result.executed_actions[0].action_type == "restart_service"


def test_allowed_actions_are_executed_in_simulation():
    dispatcher = Dispatcher()
    actions = [
        Action(
            id="issue-1:inspect_process",
            action_type="inspect_process",
            issue_id="issue-1",
            target="pid:4888",
            description="Inspect suspicious process",
            allowed=True,
            execution_mode="observe_only",
        )
    ]

    dispatch_result = dispatcher.dispatch(actions)

    assert len(dispatch_result.executed_actions) == 1
    assert dispatch_result.executed_actions[0].executed is True
    assert dispatch_result.executed_actions[0].success is True
    assert "Simulated process inspection completed" in dispatch_result.executed_actions[0].message


def test_dispatcher_returns_only_executed_allowed_actions():
    dispatcher = Dispatcher()
    actions = [
        Action(
            id="issue-1:restart_service",
            action_type="restart_service",
            issue_id="issue-1",
            target="cache",
            description="Restart cache service",
            allowed=True,
            execution_mode="simulate_only",
        ),
        Action(
            id="issue-2:stop_conflicting_process",
            action_type="stop_conflicting_process",
            issue_id="issue-2",
            target="port:5432",
            description="Stop conflicting process",
            allowed=True,
            execution_mode="blocked",
        ),
        Action(
            id="issue-3:inspect_port_usage",
            action_type="inspect_port_usage",
            issue_id="issue-3",
            target="port:5432",
            description="Inspect port usage",
            allowed=True,
            execution_mode="observe_only",
        ),
    ]

    dispatch_result = dispatcher.dispatch(actions)

    assert len(dispatch_result.executed_actions) == 2
    assert {result.action_type for result in dispatch_result.executed_actions} == {
        "restart_service",
        "inspect_port_usage",
    }
