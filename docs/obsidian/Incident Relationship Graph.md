---
title: Incident Relationship Graph
tags:
  - Incidents
  - HostGraph
  - Playbooks
  - Remediation
---

# Incident Relationship Graph

Two graph API views are now exposed:

- `GET /graph/current`
- `GET /graph/incident/{incident_key}`

## Current graph

`/graph/current` returns host-wide connected nodes/edges for the selected platform/mode context and includes:

- host entities
- current issues
- correlated incidents
- planned actions from policy-classified candidates

## Incident-scoped graph

`/graph/incident/{incident_key}` focuses on incident-linked nodes and direct dependencies.

- incident node is anchor
- related issue/action targets are included
- host node is retained for context
- host fan-out expansion is constrained to avoid noisy full-graph spillover

## Purpose

The incident-scoped graph supports operator triage and dashboard highlighting without introducing a full graph editor.

[[Command Orchestration Model]]
[[Incident State Machine]]
[[Host Graph Model]]
[[Dependency Mapping Design]]
[[Incident Relationship Graph]]
