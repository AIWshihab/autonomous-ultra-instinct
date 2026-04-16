# Policy Matrix

This matrix documents policy decisions for automated repair actions.

| Action Type | Risk Tier | Execution Mode | Approval Required | Default Policy |
|-------------|-----------|----------------|-------------------|----------------|
| restart_service | medium | simulate_only | true | Approval required for containment actions |
| clear_temp_files | low | execute_when_safe | false | Auto-approved if not blocked |
| inspect_process | low | simulate_only | false | Allowed for investigation |
| quarantine_process | high | blocked | true | Blocked unless explicitly approved |
| collect_forensic_snapshot | medium | simulate_only | true | Approval required for forensic capture |

## Policy Notes

- `simulate_only` means the action is traced but not actually executed in live mode.
- High-risk actions are blocked by default and need explicit operator approval.
- Confidence metadata is used to help surface policy rationale to reviewers.
