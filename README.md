# Autonomous Repair Agent

A cross-platform Python scaffold for a safe autonomous system repair agent.

This repository provides a backend-first foundation for observing system state, detecting issues, planning safe remediation actions, enforcing deterministic policy, and recording audit-friendly decision traces.

## What is included

- FastAPI app entrypoint
- Shared Pydantic models for system info, resources, processes, services, state snapshots, actions, and verification results
- Core modules for state management, planning, policy evaluation, dispatch, execution simulation, and verification
- Adapter interfaces for Linux, Windows, and macOS
- Rule-based issue detection and policy classification
- Decision trace support for detection, planning, policy, dispatch, execution, and verification stages
- UI dashboard assets in `static/` and `templates/`
- Obsidian vault scaffolding in `.obsidian/`
- Project documentation notes in `Notes/`
- API routes: `/health`, `/snapshot`, `/plan`, `/execute`
- Unit tests for full flow validation

## API Endpoints

- `GET /snapshot` — collect telemetry and return the current snapshot
- `GET /plan` — generate candidate actions and evaluate policy decisions
- `GET /execute` — dispatch allowed actions and return execution plus verification results

## Run locally

```bash
cd '/Users/user/Documents/project 111'
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

## Run tests

```bash
cd '/Users/user/Documents/project 111'
.venv/bin/python -m pytest -q
```

## Notes and documentation

- Use the `Notes/` folder for project documentation and operational runbooks
- The `.obsidian/` folder contains vault settings for Obsidian
- See `Notes/Design Decisions.md`, `Notes/Policy Matrix.md`, and `Notes/Testing Strategy.md` for implementation context
