---
title: Event History Model
tags:
  - EventHistory
  - Persistence
  - AuditTrail
  - DecisionTraceModel
  - SQLitePersistenceDesign
---

# Event History Model

This implementation uses a lightweight SQLite-backed event store for the autonomous repair agent.

## What gets persisted

Each event record stores:

- `event_id` — deterministic identifier generated from the UTC timestamp and event type.
- `event_type` — one of `snapshot_event`, `plan_event`, or `execute_event`.
- `platform` — target platform at the time of the event.
- `mode` — execution mode (`mock` or `live`).
- `created_at` — exact UTC timestamp when the event was recorded.
- `health_score` and `risk_score` — the operational posture metrics from the snapshot.
- `issue_count` — number of detected issues in the snapshot.
- `payload_json` — full structured serialized event payload, including issues, actions, policy classifications, execution results, decision trace, and audit trail.

## Why these fields matter

- `event_type` and `platform` enable timeline filtering for incident review.
- `created_at` makes the history timeline sortable and replayable.
- `health_score` and `risk_score` provide immediate context for severity and trending.
- `payload_json` stores the entire event record so the system can reconstruct the exact decision state and audit trail later.

## Implementation details

- Stored in `app/core/history_repository.py`.
- The repository uses a single SQLite table named `event_history`.
- Records are persisted through `app/core/history_service.py`.
- The service is invoked from the API routes in `app/api/routes.py` after `/snapshot`, `/plan`, and `/execute`.

## Future correlation and analytics

This model is intentionally simple but extensible.

Future work can add:

- a separate table for issues, actions, or audit stages for faster queries
- time-series queries for health/risk trends
- correlation keys for repeated incident types
- event linking across sessions using issue IDs or decision trace metadata

[[Timeline and Incident Replay]]
