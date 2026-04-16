---
title: Command Orchestration Model
tags:
  - RuntimeObservation
  - CommandOrchestration
  - SafetyBoundary
  - Auditability
---

# Command Orchestration Model

macOS live observation now runs through a governed orchestration layer instead of ad-hoc command calls.

## Implemented control objects

- `ObservationTask`
- `ObservationBatch`
- `AllowedCommand`
- `CommandPolicyDecision`
- `CommandInvocation`
- `CommandResult`
- `RuntimeObservationTrace`

## Core flow

1. Observation task is requested (`collect_system_identity`, `collect_resource_usage`, etc.).
2. Task maps to predefined command specs (no raw command input surface).
3. Runtime command policy evaluates each command against strict allowlist.
4. Allowlisted command executes with direct argv invocation (`shell=False`).
5. Output is parsed into structured task artifacts.
6. Invocation/result records are persisted for audit and replay.

## Design intent

- observation abstraction first, command strings second
- deterministic command governance
- partial failure tolerance with explicit warnings
- auditable payload attached to snapshots and API traces

[[Approval Workflow Design]]
[[Human in the Loop Safety Model]]
[[Command Orchestration Model]]
[[Allowlisted Runtime Observation]]
[[Runtime Command Policy]]
