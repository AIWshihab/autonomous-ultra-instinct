---
title: Human in the Loop Safety Model
tags:
  - HumanInLoop
  - Safety
  - Governance
  - Remediation
---

# Human in the Loop Safety Model

The control plane now separates autonomous observation from human-governed remediation authority.

## Why approval exists

- Observation can be autonomous when read-only and low risk.
- Remediation with operational impact requires explicit operator intent.
- Live-mode medium/high actions are constrained behind approval gates.

## Safety insertion points

Approval is inserted between planning and dispatch:

1. planner builds strategy + candidate actions
2. policy classifies risk and execution mode
3. approval policy evaluates human-governance requirement
4. approval request is persisted when required
5. dispatcher executes only approved and non-blocked actions

## Guardrail outcomes

- pending approval -> execution halted for gated actions
- denied approval -> action blocked and incident transitions to denied/blocked
- expired approval -> action blocked until renewal/new request

## Future extensions

- role-based approvals
- dual-operator or quorum workflows
- scoped approver permissions by platform/risk tier

[[Incident State Machine]]
[[Remediation Playbook Model]]
[[Approval Workflow Design]]
[[Operator Control Plane]]
[[Human in the Loop Safety Model]]
