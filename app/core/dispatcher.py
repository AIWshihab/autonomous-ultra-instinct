from typing import List

from app.executors.shell_executor import ShellExecutor
from app.models.schemas import Action, DispatchResult


class Dispatcher:
    """Dispatch allowed actions to the simulation executor."""

    def __init__(self, executor: ShellExecutor | None = None) -> None:
        self.executor = executor or ShellExecutor()

    def dispatch(self, actions: List[Action]) -> DispatchResult:
        execution_results = []
        dispatched_actions = []

        for action in actions:
            if action.allowed is True and action.execution_mode != "blocked":
                dispatch_reason = "Allowed by policy and safe to simulate."
                dispatched_action = action.model_copy(update={"dispatch_reason": dispatch_reason})
                execution_results.append(self.executor.execute(dispatched_action))
                dispatched_actions.append(dispatched_action)
            else:
                dispatch_reason = (
                    "Skipped because the action was blocked by policy."
                    if action.execution_mode == "blocked" or action.allowed is not True
                    else "Not dispatched due to policy state."
                )
                dispatched_actions.append(action.model_copy(update={"dispatch_reason": dispatch_reason}))

        return DispatchResult(executed_actions=execution_results, actions=dispatched_actions)
