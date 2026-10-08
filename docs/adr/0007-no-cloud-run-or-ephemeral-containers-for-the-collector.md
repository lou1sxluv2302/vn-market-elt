# ADR-0007: No Cloud Run or ephemeral containers for the collector

- Status: Accepted
- Date: 2026-10-06
- Spec: D7

## Context

vnstock identifies a device by an id stored in a file. A fresh container may register a new device each start until the plan's per-OS limit returns HTTP 429.

## Decision

Use a VM with a persistent disk; register the device once.

## Consequences

Container-based deployment is off the table for the collector.
