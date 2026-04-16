---
title: Operational Runbook
aliases: ["Runbook", "Operations Guide"]
tags: [project111, obsidian, operations, runbook]
---

# Operational Runbook

This document describes how to operate, troubleshoot, and monitor the autonomous repair agent.

## Daily checks

- Confirm the service is running and responding on the expected port.
- Review the latest snapshot, plan, and execute traces for anomalous decisions.
- Validate that issue detection is not generating false positives.

## Incident response

- If the agent proposes a blocked or approval-required action, escalate to a human reviewer.
- For unstable hosts, inspect the snapshot telemetry and issue evidence before making changes.
- Use the log output in `static/dashboard.js` and server logs for debugging.

## Maintenance tasks

- Update detectors as new issue patterns appear.
- Refresh policy rules based on risk posture and operational experience.
- Run full test suite after any change: `python -m pytest -q`.

## See also

- [[Deployment Checklist]]
- [[Issue Catalog]]
- [[Project Notes]]
