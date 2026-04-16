from app.models.schemas import Action, ExecutionResult


class ShellExecutor:
    """Simulation-only executor for safe action testing."""

    simulation_messages = {
        "restart_service": "Simulated service restart completed",
        "inspect_port_usage": "Simulated port inspection completed",
        "inspect_process": "Simulated process inspection completed",
        "collect_forensic_snapshot": "Simulated forensic snapshot collected",
    }

    def execute(self, action: Action) -> ExecutionResult:
        dispatch_reason = action.dispatch_reason or "Dispatch decision not recorded."
        if action.allowed is not True or action.execution_mode == "blocked":
            message = "Skipped because the action was blocked by policy."
            return ExecutionResult(
                action_id=action.id,
                issue_id=action.issue_id,
                action_type=action.action_type,
                target=action.target,
                allowed=False,
                executed=False,
                success=False,
                message=message,
                execution_message=message,
                execution_stage="skipped",
                dispatch_reason=dispatch_reason,
            )

        message = self.simulation_messages.get(action.action_type)
        if message is None:
            message = "Simulation for this action type is not implemented."
            return ExecutionResult(
                action_id=action.id,
                issue_id=action.issue_id,
                action_type=action.action_type,
                target=action.target,
                allowed=True,
                executed=False,
                success=False,
                message=message,
                execution_message=message,
                execution_stage="simulation_unavailable",
                dispatch_reason=dispatch_reason,
            )

        return ExecutionResult(
            action_id=action.id,
            issue_id=action.issue_id,
            action_type=action.action_type,
            target=action.target,
            allowed=True,
            executed=True,
            success=True,
            message=message,
            execution_message=message,
            execution_stage="simulated_execution",
            dispatch_reason=dispatch_reason,
        )
