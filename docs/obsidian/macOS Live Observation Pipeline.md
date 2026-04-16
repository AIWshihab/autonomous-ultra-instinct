---
title: macOS Live Observation Pipeline
tags:
  - macOS
  - LiveMode
  - RuntimePipeline
  - AdapterArchitecture
---

# macOS Live Observation Pipeline

`MacOSAdapter` now delegates live observation to `RuntimeObservationService` for governed execution.

## Pipeline implementation

1. Adapter checks host platform (`Darwin`).
2. Runtime service runs task batch:
   - `collect_system_identity`
   - `collect_resource_usage`
   - `collect_processes`
   - `collect_open_ports`
   - `collect_disk_usage`
3. Task outputs are parsed into structured artifacts.
4. Artifacts are transformed into `StateSnapshot`.
5. `runtime_observation_trace` is embedded in snapshot for API/UI/audit use.
6. Trace is persisted via runtime observation repository.

## Failure model

- command failures are captured as `CommandResult(success=false)`
- task parser can still produce partial artifact
- batch is marked `partial_failure=true` when any task does not fully succeed
- warnings are propagated into trace and snapshot logs

## Safety separation

- observation pipeline is read-only and allowlisted
- remediation actions still run under policy + approval governance

[[Approval Workflow Design]]
[[Human in the Loop Safety Model]]
[[Command Orchestration Model]]
[[Allowlisted Runtime Observation]]
[[Runtime Command Policy]]
