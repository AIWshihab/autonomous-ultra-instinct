---
title: Decision Competition Model
tags:
  - DecisionModel
  - StrategyRanking
  - IncidentControlPlane
---

# Decision Competition Model

The planner now runs strategy competition first, then maps the winning strategy into actionable playbook flow.

## Implemented control-plane sequence

1. detector/scoring produce issue context
2. strategy engine builds candidate set by issue type
3. strategy ranking selects winner and preserves alternatives
4. planner emits winner actions (+ blocked preview alternatives)
5. policy classifies actions
6. playbook/state-machine + approval workflow consume selected path

## Deterministic tie-breaking

When two strategies have equal score:

- higher priority: total score descending
- stable tie-break: `strategy_id` ascending

This guarantees reproducible selection under identical inputs.

## Graph linkage

Selected strategy nodes are now linked in host graph:

- `incident -> strategy`
- `issue -> strategy`
- `strategy -> action`
- `action -> target entity`

[[Remediation Playbook Model]]
[[Incident State Machine]]
[[Host Graph Model]]
[[Strategy Engine Model]]
[[Strategy Tradeoff Rules]]
[[Explainable Remediation Selection]]
