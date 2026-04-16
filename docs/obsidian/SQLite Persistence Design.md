---
title: SQLite Persistence Design
tags:
  - SQLite
  - Persistence
  - EventHistory
  - DatabaseDesign
---

# SQLite Persistence Design

A minimal SQLite persistence layer was added for V1 event history.

## Layered architecture

- `app/core/history_repository.py` handles raw SQLite operations and table creation.
- `app/core/history_service.py` provides the event-specific persistence API.
- `app/api/routes.py` uses the service for snapshot, plan, and execute events.

## Schema

Single table: `event_history`

Columns:

- `event_id` TEXT PRIMARY KEY
- `event_type` TEXT NOT NULL
- `platform` TEXT NOT NULL
- `mode` TEXT NOT NULL
- `created_at` TEXT NOT NULL
- `health_score` INTEGER NOT NULL
- `risk_score` INTEGER NOT NULL
- `issue_count` INTEGER NOT NULL
- `payload_json` TEXT NOT NULL

## Why SQLite

- deterministic local storage without an ORM
- easy to inspect with standard SQLite tools
- simple, durable, and appropriate for V1

## Next steps

A future revision can introduce:

- separate normalized issue or action tables
- query indexes on `event_type`, `platform`, `mode`, and `created_at`
- additional metadata columns for event correlation

[[Event History Model]]
[[Timeline and Incident Replay]]
