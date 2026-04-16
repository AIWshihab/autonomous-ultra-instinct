---
title: Allowlisted Runtime Observation
tags:
  - Allowlist
  - RuntimeSafety
  - macOS
  - ReadOnlyObservation
---

# Allowlisted Runtime Observation

The runtime observation boundary is enforced by a strict, centralized command allowlist for `platform=macos` and `mode=live`.

## Current allowlisted commands

- `hostname`
- `sw_vers -productVersion`
- `uname -s`
- `sysctl -n kern.boottime`
- `sysctl -n hw.memsize`
- `vm_stat`
- `ps -A -o %cpu=`
- `ps -Arc -o pid=,comm=,%cpu=,rss=,state=`
- `df -k /`
- `lsof -nP -iTCP -sTCP:LISTEN`
- `netstat -anv -p tcp` (fallback)

## Explicitly excluded behavior

- no arbitrary command execution
- no shell interpolation
- no user-provided raw command input
- no write/destructive commands (`rm`, `mv`, `cp`, `touch`, etc.)
- no `sudo`
- no process kill/network mutation commands

## Why this matters

- shrinks runtime blast radius
- preserves explainability for every invocation
- keeps live-mode observation separated from remediation authority

[[Approval Workflow Design]]
[[Human in the Loop Safety Model]]
[[Command Orchestration Model]]
[[Allowlisted Runtime Observation]]
[[Runtime Command Policy]]
