---
title: Approval Workflow Design
tags:
  - Approval
  - Governance
  - ControlPlane
  - Safety
---

# Approval Workflow Design

Approval is now a first-class control-plane workflow with deterministic policy evaluation, persisted requests, persisted decisions, and explicit state effects.

## Domain objects implemented

- `ApprovalRequest`
- `ApprovalDecision`
- `ApprovalQueueItem`
- `ApprovalPolicy`
- `OperatorDecisionTrace`
- `ApprovalSummary`

## Core rules in V1

- Approval required for:
  - `restart_service` in live mode
  - medium/high-risk live-mode remediation
  - any playbook step in explicit `approval_pending` state
- Approval not required for:
  - low-risk observe-only steps
  - safe mock-mode simulation steps
- Blocked actions remain non-escalatable in V1.

## Persistence design

- SQLite tables:
  - `approval_requests`
  - `approval_decisions`
- Requests include incident/playbook/step/action context, policy reason, state snapshot, and TTL.
- Decisions include operator action (`approve`/`deny`), prior status, resulting status, and timestamp.

[[Incident State Machine]]
[[Remediation Playbook Model]]
[[Approval Workflow Design]]
[[Operator Control Plane]]
[[Human in the Loop Safety Model]]
