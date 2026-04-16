---
title: Strategy Selection Rules
tags:
  - Strategy
  - PlaybookSelection
  - DeterministicRules
  - Priority
---

# Strategy Selection Rules

The planner now selects remediation strategies from a deterministic playbook library.

## Inputs used

- issue type
- severity
- priority score
- recurrence status/count
- baseline/deviation context (when present)

## Selection logic (V1)

- Primary key: `issue.type` -> matching playbook.
- If no exact playbook exists, use fallback observability playbook.
- Issue ordering remains priority-first:
  - descending `priority_score`
  - stable tie-break by issue id
- Selection reason is written into `RemediationStrategy.selection_reason` for auditability.

## Policy and strategy interaction

- Strategy defines ordered steps and intended actions.
- Policy engine classifies action safety metadata (`risk_tier`, approval, execution mode).
- Playbook engine projects policy outcomes into:
  - step status (`ready`, `approval_pending`, `blocked`, `verified`, `failed`)
  - incident state transitions

## Current boundaries

- deterministic mapping only (no ML/LLM playbook routing)
- no dynamic optimization loops yet
- no real write-path execution yet

[[Incident Grouping Design]]
[[Baseline Engine Model]]
[[Remediation Playbook Model]]
[[Incident State Machine]]
[[Verification Checkpoint Design]]
