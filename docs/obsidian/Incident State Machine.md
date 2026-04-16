---
title: Incident State Machine
tags:
  - IncidentState
  - StateMachine
  - SafetyControlPlane
  - Remediation
---

# Incident State Machine

Incidents and playbook executions now use a formal transition model with explicit allowed transitions and reasons.

## Implemented states

- `detected`
- `analyzed`
- `planned`
- `approval_pending`
- `approved`
- `blocked`
- `dispatched`
- `executed`
- `verified`
- `failed`
- `closed`

## Transition behavior in code

`IncidentStateMachine` enforces allowed transitions. Invalid transitions raise `InvalidStateTransitionError`.

Core V1 paths:

1. Planning path:
   - `detected -> analyzed -> planned -> (approved | approval_pending | blocked)`
2. Execution path:
   - approved path continues:
   - `approved -> dispatched -> executed -> (verified -> closed | failed)`
3. Blocked path:
   - `planned -> blocked` when all relevant actions are policy blocked.

## Data attached to each incident state

- `current_state`
- `previous_state`
- `allowed_transitions`
- `transition_reason`
- `updated_at`
- transition timeline (`StepTransition[]`)

## Notes

- In simulation mode, approval-required actions can auto-transition `approval_pending -> approved` to preserve deterministic flow testing.
- For real execution later, this auto-approval must be replaced by human approval events.

[[Incident Grouping Design]]
[[Baseline Engine Model]]
[[Remediation Playbook Model]]
[[Incident State Machine]]
[[Verification Checkpoint Design]]
