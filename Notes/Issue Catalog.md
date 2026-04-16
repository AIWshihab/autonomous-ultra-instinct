---
title: Issue Catalog
aliases: ["Issue Reference", "Detection Catalog"]
tags: [project111, obsidian, issues, detection]
---

# Issue Catalog

A reference of issue types and their expected evidence patterns.

## Issue Types

### service-down
- Category: availability
- Severity: high
- Evidence: service status down, repeated failures, process absence
- Typical remediation: restart service, inspect logs

### suspicious-process
- Category: security
- Severity: high
- Evidence: unknown process, high CPU usage, unauthorized binary
- Typical remediation: inspect process, quarantine process

### high-memory-usage
- Category: resource
- Severity: medium
- Evidence: memory used above threshold, repeated spikes
- Typical remediation: clear temp files, restart service

### open-port-exposure
- Category: network
- Severity: medium
- Evidence: unexpected listening port, public exposure
- Typical remediation: audit service, update firewall rules

## Catalog usage

This note helps developers and operators understand what issues the agent detects and why. It can be extended as new detectors are added.

## See also

- [[Implementation Guide]]
- [[Policy Matrix]]
- [[Project Notes]]
