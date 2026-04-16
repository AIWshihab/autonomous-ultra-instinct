# Autonomous Repair Agent

A minimal Python scaffold for a cross-platform autonomous system repair agent.

This project is a backend-first foundation for observing system state, detecting limited issues, planning safe repair actions, and logging audit trails.

## What is included

- FastAPI app entrypoint
- Shared Pydantic models for system info, resources, processes, services, and state snapshots
- Core modules for state management, planning, policy, verification, dispatch, and audit logging
- Adapter interfaces for Linux, Windows, and macOS
- Observer and detector base interfaces
- Shell executor stub with strict safety guidance
- API routes: `/health` and `/snapshot`
- Unit tests for API and schema validation

## Run locally

```bash
cd '/Users/user/Documents/project 111'
python -m uvicorn app.main:app --reload --port 8000
```

## Run tests

```bash
cd '/Users/user/Documents/project 111'
python -m pytest -q
```
