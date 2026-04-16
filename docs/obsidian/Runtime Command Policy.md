---
title: Runtime Command Policy
tags:
  - RuntimePolicy
  - CommandGovernance
  - SafetyClass
  - Audit
---

# Runtime Command Policy

`RuntimeCommandPolicy` provides deterministic allow/deny decisions for command invocations.

## Policy decision fields

- `command_name`
- `args`
- `allowed`
- `reason`
- `safety_class`
- `platform`
- `mode`

## Policy behavior

- only `macos` + `live` evaluated for allowlisted observation commands
- command + exact args must match allowlist entry
- anything outside allowlist is denied with explicit reason
- denied invocations are still recorded in trace for audit visibility

## Safety classes used

- `identity`
- `resource`
- `process`
- `storage`
- `network`
- `denied`

## Expansion path

- add new tasks first
- map tasks to bounded command specs
- extend allowlist only after policy review and parser coverage

[[Approval Workflow Design]]
[[Human in the Loop Safety Model]]
[[Command Orchestration Model]]
[[Allowlisted Runtime Observation]]
[[Runtime Command Policy]]
