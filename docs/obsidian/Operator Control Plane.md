---
title: Operator Control Plane
tags:
  - Operator
  - SOC
  - Governance
  - Dashboard
---

# Operator Control Plane

The dashboard now contains an Approval Center for operator-governed remediation control.

## Implemented panels

- Pending approval queue:
  - incident context
  - playbook + step context
  - action/risk/confidence/policy reason
  - approval and denial actions
- Recent decisions:
  - approved/denied result
  - decision reason
  - timestamp and linked request

## API backing

- `GET /approvals`
- `GET /approvals/recent`
- `GET /approvals/{request_id}`
- `POST /approvals/{request_id}/approve`
- `POST /approvals/{request_id}/deny`

## Control-plane behavior

- `/plan` surfaces approval-gated steps.
- `/execute` blocks approval-gated actions when requests are pending/denied/expired.
- Operator decisions feed back into incident state and playbook progression.

[[Incident State Machine]]
[[Remediation Playbook Model]]
[[Approval Workflow Design]]
[[Operator Control Plane]]
[[Human in the Loop Safety Model]]
