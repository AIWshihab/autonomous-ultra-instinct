# Architecture Overview

This repository contains the first scaffold of a cross-platform autonomous system repair agent.

## Key components

- `app/main.py` - FastAPI entrypoint and route registration
- `app/api/routes.py` - HTTP route definitions
- `app/models/schemas.py` - Shared data models for snapshots, issues, actions, and verification
- `app/core/` - Core orchestration modules for state, planning, policy, verification, dispatch, and audit logging
- `app/adapters/` - OS adapter interfaces and platform-specific adapter stubs
- `app/observers/` - Observer interface for system state collection
- `app/detectors/` - Detector interface for issue identification
- `app/executors/` - Shell executor stub for bounded command execution

## Design principles

- clear separation between shared core logic and platform-specific adapters
- minimal, safe, and extensible scaffold
- no database, no UI, no LLM integration, no unsafe shell execution
- explicit placeholders for future implementations
