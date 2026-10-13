# ADR-0023: Stock-selection research before streaming, in a private repository

- Status: Accepted
- Date: 2026-10-08 · amended 2026-10-13 (research moved to a private repository)
- Spec: D23

## Context

The owner's priority is a stock-selection research track. Its hypotheses,
features and results are a private asset. Streaming (S0-S3) serves a different
goal - intraday latency - and is not urgent.

## Decision

Run the research track in a **private companion repository** that reads this
project's marts. Schedule it after the cold path (P1-P3) and before streaming.

## Consequences

This repository publishes only the data foundation and the research discipline
(ADR-0024). `v1.0.0` moves to ~2026-12-09.
