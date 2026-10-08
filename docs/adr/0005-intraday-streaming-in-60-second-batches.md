# ADR-0005: Intraday streaming in 60-second batches

- Status: Accepted
- Date: 2026-10-06
- Spec: D5

## Context

The batch chain takes 62–79 minutes, mostly waiting on an API. The goal is ≤ 5 minutes of latency during the session.

## Decision

Capture the VPS WebSocket feed and write a parquet batch every 60 seconds.

## Consequences

A process must run for the whole session; missed sessions are lost forever, so health alerts are mandatory.
