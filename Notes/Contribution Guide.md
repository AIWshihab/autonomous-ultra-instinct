---
title: Contribution Guide
aliases: ["Contributing Guide", "Contributing"]
tags: [project111, obsidian, contribution, collaboration]
---

# Contribution Guide

Guidelines for contributing to the autonomous repair agent project.

## Getting started

- Fork the repository and clone it locally.
- Use the provided `.venv` virtual environment for development.
- Install dependencies from `requirements.txt`.
- Run tests before submitting a pull request.

## Code standards

- Keep modules small and focused.
- Add meaningful trace/reason fields for every new issue or action.
- Avoid real destructive actions; prefer safe simulation and mock flows.

## Documentation

- Add or update markdown notes in `Notes/` for any new feature or design change.
- Keep `README.md`, `ARCHITECTURE.md`, and `AGENTS.md` aligned with implementation.

## Workflow

- Branch from `main` with descriptive branch names.
- Use clear commit messages and include relevant issue references.
- Open a pull request with a summary of the change and validation steps.

## See also

- [[Testing Strategy]]
- [[Project Notes]]
