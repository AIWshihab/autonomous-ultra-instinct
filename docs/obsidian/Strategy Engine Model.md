---
title: Strategy Engine Model
tags:
  - StrategyEngine
  - Remediation
  - Explainability
  - DeterministicScoring
---

# Strategy Engine Model

`StrategyEngine` now performs deterministic multi-candidate competition per issue before playbook execution.

## Implemented objects

- `StrategyCandidate`
- `StrategyScore`
- `StrategySelection`
- `StrategyTradeoff`
- `StrategyEvaluationContext`
- `StrategyDecisionTrace`

## Runtime flow

1. Build strategy candidates for issue type + target.
2. Evaluate each candidate with policy-aware action previews for current platform/mode.
3. Score each candidate across weighted dimensions.
4. Rank deterministically (`total_score desc`, then `strategy_id asc`).
5. Emit winner, ranked alternatives, winning reason, and rejected reasons.

## Implemented candidate families

- `SERVICE_DOWN`: restart-oriented, evidence-first defer, runtime-refresh restart
- `PORT_CONFLICT`: investigate+evidence, stop proposal, containment recommendation
- `SUSPICIOUS_PROCESS`: evidence-first, quarantine proposal, escalation-only
- `DISK_PRESSURE`: observe+alert, cleanup proposal, monitoring strategy
- `HIGH_RESOURCE_USAGE`, `CRASH_LOOP`: multiple deterministic options

[[Remediation Playbook Model]]
[[Incident State Machine]]
[[Host Graph Model]]
[[Strategy Engine Model]]
[[Strategy Tradeoff Rules]]
[[Explainable Remediation Selection]]
