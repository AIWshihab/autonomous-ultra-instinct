---
title: Dependency Mapping Design
tags:
  - HostGraph
  - DependencyMapping
  - RuleBasedModel
---

# Dependency Mapping Design

The graph layer derives deterministic relationships from existing control-plane state.

## Implemented mapping rules

- Host `contains` services, processes, ports, issues, incidents
- Process `listens_on` port (default map + explicit log hints when available)
- Service `depends_on` process runtime and known service ports
- Issue `targets` service/process/port based on issue target parsing
- Incident `contains` issue nodes linked by `incident_key`
- Issue `executes` action candidates from planner/policy
- Incident `contains` action nodes selected by remediation strategy linkage
- Runtime observation adds `related_to` edges from host to process/port artifacts

## Constraints

- deterministic and explainable only
- no inferred hidden topology from external scanners
- no persistence to graph DB in V1

[[Command Orchestration Model]]
[[Incident State Machine]]
[[Host Graph Model]]
[[Dependency Mapping Design]]
[[Incident Relationship Graph]]
