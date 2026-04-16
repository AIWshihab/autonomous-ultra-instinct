from app.models.schemas import ExecutionResult, VerificationResult


class Verifier:
    """Verify that an action has achieved the expected outcome."""

    def verify(self, execution_result: ExecutionResult) -> VerificationResult:
        verified = execution_result.success is True
        reason = (
            "Verified because the simulated execution reported success."
            if verified
            else "Verification failed because the simulated execution did not succeed."
        )
        basis = (
            "Based on the simulated execution success flag and auditable runtime status."
            if verified
            else "Based on the simulated execution failure state."
        )

        return VerificationResult(
            action_id=execution_result.action_id,
            issue_id=execution_result.issue_id,
            action_type=execution_result.action_type,
            verified=verified,
            reason=reason,
            verification_basis=basis,
        )
