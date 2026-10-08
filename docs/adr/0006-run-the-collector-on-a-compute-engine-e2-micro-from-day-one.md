# ADR-0006: Run the collector on a Compute Engine e2-micro from day one

- Status: Accepted
- Date: 2026-10-06
- Spec: D6

## Context

The collector needs a long-lived process with a stable disk. Compute Engine's free tier includes one e2-micro in a US region.

## Decision

Run on e2-micro in `us-central1`; keep GCS and BigQuery in `US`.

## Consequences

~200 ms round trip to Vietnam is irrelevant for a 5-minute target. Whether the feed accepts non-Vietnamese IPs is tested at the S0 gate.
