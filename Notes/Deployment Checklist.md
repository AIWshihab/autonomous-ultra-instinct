---
title: Deployment Checklist
aliases: ["Deployment Guide", "Release Checklist"]
tags: [project111, obsidian, deployment, ops]
---

# Deployment Checklist

This checklist covers essential steps before deploying the autonomous repair agent.

- [ ] Verify the target environment supports Python and required dependencies.
- [ ] Confirm the `.venv` environment is set up and dependencies are installed.
- [ ] Run `python -m pytest -q` and ensure all tests pass.
- [ ] Review the `README.md` and operational notes for current setup instructions.
- [ ] Validate any platform-specific collection adapters for Linux, Windows, and macOS.
- [ ] Ensure the GitHub repository contains the latest code and documentation.
- [ ] Confirm that the Obsidian vault is accessible if team documentation is required.

## See also

- [[Operational Runbook]]
- [[Project Notes]]
