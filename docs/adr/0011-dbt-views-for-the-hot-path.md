# ADR-0011: dbt views for the hot path

- Status: Accepted
- Date: 2026-10-06
- Spec: D11

## Context

With manual refresh, a cron that rebuilds tables every few minutes adds latency and cost.

## Decision

Hot-path marts are dbt views over today's partition.

## Consequences

Latency equals the batch interval. Slow views are switched to incremental individually, based on measurements.
