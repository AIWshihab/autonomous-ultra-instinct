---
title: Timeline and Incident Replay
tags:
  - IncidentTimeline
  - History
  - Replay
  - AuditTrailDesign
  - DecisionTraceModel
---

# Timeline and Incident Replay

The dashboard now includes a History Timeline panel that reads from persisted event history.

## How replay works

1. The backend records every `/snapshot`, `/plan`, and `/execute` request into SQLite.
2. `/history/recent` returns the latest timeline items for the UI.
3. Selecting an item loads `/history/{event_id}` and renders the stored payload.

## What the incident timeline shows

- `event_type` — snapshot, plan, or execute
- timestamp and `created_at`
- `platform` and `mode`
- `health_score` and `risk_score`
- `issue_count`
- quick status badges for operational posture

## Value for operators

- replay a past plan or execution without rerunning any actions
- inspect the audit trail and decision trace that produced each recommended action
- compare event posture across time and modes

## Implementation notes

- UI timeline logic is in `/static/dashboard.js`
- layout and detail canvas are in `/templates/dashboard.html`
- history route behavior is in `app/api/routes.py`

[[Event History Model]]
[[SQLite Persistence Design]]
