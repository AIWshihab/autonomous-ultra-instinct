---
title: Host Graph Model
tags:
  - HostGraph
  - DependencyMapping
  - IncidentResponse
  - ControlPlane
---

# Host Graph Model

The control plane now exposes a computed `HostGraph` object for connected host context.

## Implemented graph primitives

- `NodeType`: `host`, `service`, `process`, `port`, `issue`, `incident`, `action`
- `EdgeType`: `depends_on`, `listens_on`, `targets`, `contains`, `executes`, `related_to`
- `GraphNode`: `id`, `type`, `label`, `attributes`, optional `severity`
- `GraphEdge`: `source_id`, `target_id`, `type`, `description`
- `HostGraph`: `nodes`, `edges`, `metadata`

## V1 architecture

`HostGraphBuilder` builds graph state in memory from current runtime objects:

1. host snapshot entities (services/processes/ports)
2. detector-produced issues
3. correlated incidents
4. planner/policy actions
5. runtime observation trace hints (for macOS live)

No graph database is used in V1.

[[Command Orchestration Model]]
[[Incident State Machine]]
[[Host Graph Model]]
[[Dependency Mapping Design]]
[[Incident Relationship Graph]]
