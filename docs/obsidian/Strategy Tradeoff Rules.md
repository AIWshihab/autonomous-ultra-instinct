---
title: Strategy Tradeoff Rules
tags:
  - StrategyEngine
  - Tradeoffs
  - ApprovalBurden
  - DisruptionModel
---

# Strategy Tradeoff Rules

## Weighted score dimensions (implemented)

- Positive:
  - `severity_alignment` (0.15)
  - `confidence_support` (0.09)
  - `recurrence_pressure` (0.08)
  - `chronicity_pressure` (0.09)
  - `baseline_deviation_support` (0.08)
  - `execution_feasibility` (0.14)
  - `observability_gain` (0.14)
  - `risk_fit` (0.13)
- Negative:
  - `approval_cost` (0.05)
  - `disruption_cost` (0.05)

## Approval burden model

`approval_cost` combines:

- template approval burden estimate
- policy preview ratio of approval-gated actions
- additional live-mode caution penalty

This pushes high-approval pathways down when comparable safer options exist.

## Disruption cost model

`disruption_cost` combines:

- template disruption estimate
- blocked action ratio from policy preview
- extra live-mode penalty for high-disruption candidates

Low-confidence + high-disruption candidates are penalized further.

## Mode-aware pressure

- live mode reduces feasibility for disruptive strategies
- service/crash-loop high-pressure cases add urgency boost to restart strategies
- uncertain conditions continue to prefer evidence-rich, lower-disruption paths

[[Remediation Playbook Model]]
[[Incident State Machine]]
[[Host Graph Model]]
[[Strategy Engine Model]]
[[Strategy Tradeoff Rules]]
[[Explainable Remediation Selection]]
