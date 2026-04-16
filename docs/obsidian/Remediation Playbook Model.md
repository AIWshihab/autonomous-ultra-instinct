---
title: Remediation Playbook Model
tags:
  - Remediation
  - Playbooks
  - IncidentResponse
  - DeterministicDesign
---

# Remediation Playbook Model

The control plane now uses deterministic remediation playbooks instead of isolated one-off actions.

## Implemented model

- `Playbook` defines the issue-type strategy (`playbook_id`, `issue_type`, `name`, ordered `steps`).
- `PlaybookStep` defines each stage, optional mapped `action_type`, retry behavior, and deterministic routing:
  - `success_condition`
  - `failure_condition`
  - `retryable`
  - `next_step_on_success`
  - `next_step_on_failure`
- `RemediationStrategy` binds a scored issue to a selected playbook and records:
  - `selection_reason`
  - `priority_score`
  - `severity`
  - recurrence/baseline context

## V1 playbooks

- `SERVICE_DOWN` -> inspect process, collect evidence, propose restart, verify, close/fail.
- `PORT_CONFLICT` -> inspect port, inspect process, collect evidence, propose process stop (policy-gated), verify.
- `DISK_PRESSURE` -> inspect pressure context, collect evidence, propose temp cleanup (policy-gated), verify.
- `SUSPICIOUS_PROCESS` -> inspect process, collect forensic snapshot, propose quarantine (policy-gated), verify.
- `HIGH_RESOURCE_USAGE` -> inspect process, collect evidence, verify normalization.
- `CRASH_LOOP` -> inspect crash-loop process, collect evidence, propose restart, verify stability.

## Safety boundaries

- Playbooks are deterministic and policy-first.
- High-risk action steps (`stop_conflicting_process`, `clear_temp_files`, `quarantine_process`) stay blocked in V1.
- Live mode remains simulation-only for remediation execution.

## Current limitations

- Step execution is simulated through policy/dispatch/verification outputs.
- No real write-path, no OS mutation, and no privileged actions.
- Future real execution must insert explicit approval + rollback checkpoints per step.

[[Incident Grouping Design]]
[[Baseline Engine Model]]
[[Remediation Playbook Model]]
[[Incident State Machine]]
[[Verification Checkpoint Design]]
