---
title: Verification Checkpoint Design
tags:
  - Verification
  - Playbooks
  - SafetyChecks
  - ExecutionSimulation
---

# Verification Checkpoint Design

Verification is now modeled as a first-class playbook component through `VerificationCheckpoint`.

## Model fields

- `checkpoint_id`
- `step_id`
- `success_condition`
- `failure_condition`
- `verified` (`true`, `false`, or pending `null`)
- `reason`
- `updated_at`

## V1 behavior

- Action steps inherit checkpoint conditions from their playbook step.
- During simulated execution:
  - verified results mark checkpoint `verified=true`
  - failed results mark checkpoint `verified=false`
  - blocked steps mark checkpoint as failed with policy reason
  - missing results remain pending (`verified=null`)
- Verification-only steps (`verify-*`) aggregate related action verification outcomes.

## Why this matters

- checkpoint outcomes are explainable and deterministic
- state machine transitions can cite concrete checkpoint reasons
- timeline/UI can show which remediation stages passed vs failed

## Future real-execution path

- map checkpoints to host-side read-only probes and post-action health checks
- introduce retry windows and timeout semantics
- require manual sign-off for unresolved/high-risk checkpoint failures

[[Incident Grouping Design]]
[[Baseline Engine Model]]
[[Remediation Playbook Model]]
[[Incident State Machine]]
[[Verification Checkpoint Design]]
