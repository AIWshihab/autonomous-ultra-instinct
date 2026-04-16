---
title: Approval State Transitions
tags:
  - Approval
  - StateMachine
  - TransitionRules
  - IncidentResponse
---

# Approval State Transitions

Approval transitions are deterministic and validated in repository and state-machine layers.

## Approval request statuses

- `pending`
- `approved`
- `denied`
- `expired`
- `cancelled`

## Valid request transitions

- `pending -> approved`
- `pending -> denied`
- `pending -> expired`
- `pending -> cancelled`

All other transitions are rejected with deterministic errors.

## Incident-state integration

- `planned -> approval_pending`
- `approval_pending -> approved`
- `approval_pending -> denied`
- `approval_pending -> expired`
- `approved -> dispatched`
- `denied -> blocked` (V1 model)
- `expired -> blocked` (V1 model)

## Execution behavior

- `/execute` never bypasses pending approvals.
- Approval-gated actions are not dispatched unless request status is `approved`.

[[Incident State Machine]]
[[Remediation Playbook Model]]
[[Approval Workflow Design]]
[[Operator Control Plane]]
[[Human in the Loop Safety Model]]
