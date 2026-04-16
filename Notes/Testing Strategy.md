---
title: Testing Strategy
aliases: ["Test Plan", "QA Strategy"]
tags: [project111, obsidian, testing, qa]
---

# Testing Strategy

This note outlines the testing approach for the project.

## Test types

- Unit tests for detectors, planner, policy engine, dispatcher, and verifier.
- API tests for snapshot, plan, and execute route behavior.
- Integration tests for end-to-end mock flows and decision trace validation.

## Running tests

- Activate the project virtual environment.
- Run the full test suite with `python -m pytest -q`.
- Use focused tests during development with `python -m pytest tests/test_api.py -q`.

## Test goals

- Ensure deterministic reasoning and stable action classification.
- Verify that blocked actions never execute.
- Validate that all audit trace fields are present in API responses.

## See also

- [[Contribution Guide]]
- [[Project Notes]]
- [[Change Log]]
