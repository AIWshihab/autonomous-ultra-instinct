---
title: Implementation Guide
aliases: ["Implementation Notes", "Development Guide"]
tags: [project111, obsidian, implementation, code]
---

# Implementation Guide

This note provides a quick reference to the repository structure and core implementation flow.

## Repository structure

- `app/main.py` - FastAPI entrypoint
- `app/api/routes.py` - HTTP endpoints for snapshot, plan, and execute
- `app/core/` - Pipeline modules and business logic
- `app/models/` - Pydantic schemas and shared models
- `app/adapters/` - Platform-specific collection adapters
- `app/detectors/` - Issue detection logic
- `app/executors/` - Safe execution simulation
- `tests/` - Automated test coverage
- `static/` and `templates/` - UI/dashboard assets

## Core flow

1. Collect snapshot from a platform adapter.
2. Detect issues and build evidence-rich issue objects.
3. Generate candidate actions in the planner.
4. Evaluate actions with the policy engine.
5. Dispatch approved actions safely.
6. Verify outcomes and build decision trace entries.

## Extension points

- Add new issue detectors under `app/detectors/`.
- Add policy rules in `app/core/policy_engine.py`.
- Add execution paths in `app/executors/` with safe simulation.
- Extend API routes when additional instrumentation is required.

## See also

- [[Design Decisions]]
- [[Glossary]]
- [[Project Notes]]
