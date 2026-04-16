# AGENTS

This repository is prepared for future guided agent workflows.

## Repository structure

- `app/main.py` - FastAPI app entrypoint
- `app/api/` - API route definitions
- `app/core/` - Core orchestration modules
- `app/models/` - Shared Pydantic schemas
- `app/adapters/` - OS adapter interfaces
- `app/observers/` - Observer interface
- `app/detectors/` - Detector interface
- `app/executors/` - Shell executor stub
- `tests/` - Unit tests for core components

## Future agent instructions

1. Use the core modules and adapter interfaces to add safe state observation.
2. Implement one issue detector per OS adapter.
3. Keep all actions narrowly scoped and verify outcomes.
4. Avoid unrestricted shell execution and destructive repair commands.
5. Add new API endpoints only for instrumentation and monitoring.
