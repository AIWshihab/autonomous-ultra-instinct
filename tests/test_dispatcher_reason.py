from app.core.dispatcher import Dispatcher
from app.models.schemas import Action


def test_dispatcher_sets_dispatch_reason_on_actions():
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

    assert len(dispatch_result.actions) == 1
    assert dispatch_result.actions[0].dispatch_reason == "Allowed because the action is safe to simulate and not blocked by policy."
    assert dispatch_result.executed_actions[0].dispatch_reason == "Allowed because the action is safe to simulate and not blocked by policy."
