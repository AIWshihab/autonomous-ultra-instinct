---
title: Design Decisions
aliases: ["Architecture Decisions", "Design Notes"]
tags: [project111, obsidian, design, architecture]
---

# Design Decisions

This note captures major architectural and design decisions for the autonomous repair agent project.

## Core design choices

- Use a deterministic rule-based pipeline for issue detection, planning, policy classification, and action dispatch.
- Separate concerns across modules: detectors, planner, policy engine, dispatcher, and verifier.
- Keep all execution safe and simulated by default, with live mode only changing data collection semantics.
- Add traceable reasoning metadata to every issue and action for auditability.

## Rules and policy

- Policy decisions are not simply allow/deny; they also include risk tier, confidence, execution mode, and approval requirements.
- High-risk or containment actions require explicit approval, even if they are simulated.
- Execution dispatch must never run blocked actions.

## Future decisions

- Consider adding plugin-based issue detectors for cloud providers and infrastructure services.
- Add a policy configuration file to allow easier tuning without code edits.
- Expand the system to support multiple backends for telemetry collection.

## See also

- [[Policy Matrix]]
- [[Implementation Guide]]
- [[Project Notes]]
