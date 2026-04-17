---
title: Explainable Remediation Selection
tags:
  - Explainability
  - StrategyEngine
  - DecisionTrace
  - HumanGovernance
---

# Explainable Remediation Selection

Every strategy competition now emits transparent reasoning instead of implicit single-playbook selection.

## What is exposed

- full ranked list (`StrategyDecisionTrace[]`)
- per-candidate `StrategyScore` with dimension values
- per-dimension reason text (`dimension_reasons`)
- top benefit/cost tradeoffs (`StrategyTradeoff[]`)
- winning reason
- rejected reasons for lower-ranked alternatives

## Why this matters

- operators can see why safer paths beat disruptive ones
- approval-heavy options are visible but explicitly down-ranked when not justified
- incident handling is auditable and reproducible across runs
- strategy decisions can be reviewed without reverse-engineering hidden logic

## Current limitations

- weights and thresholds are static
- no learned adaptation from outcomes
- no multi-objective optimizer beyond deterministic weighted sum

Future extension can add policy-safe adaptive tuning while preserving explainability guarantees.

[[Remediation Playbook Model]]
[[Incident State Machine]]
[[Host Graph Model]]
[[Strategy Engine Model]]
[[Strategy Tradeoff Rules]]
[[Explainable Remediation Selection]]
