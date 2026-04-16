from app.core.verifier import Verifier
from app.models.schemas import ExecutionResult


def test_verifier_marks_successful_simulated_actions_as_verified():
    verifier = Verifier()
    execution_result = ExecutionResult(
        action_id="action-1",
        issue_id="issue-1",
        action_type="inspect_process",
        target="pid:4888",
        allowed=True,
        executed=True,
        success=True,
        message="Simulated process inspection completed",
    )

    result = verifier.verify(execution_result)

    assert result.action_id == "action-1"
    assert result.action_type == "inspect_process"
    assert result.verified is True
    assert "simulated execution reported success" in result.reason
