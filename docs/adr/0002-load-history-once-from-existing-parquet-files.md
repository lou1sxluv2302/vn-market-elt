# ADR-0002: Load history once from existing parquet files

- Status: Accepted
- Date: 2026-10-06
- Spec: D2

## Context

26 years of daily prices already exist as raw parquet in the research repo. Re-pulling them would take hours through an API key shared with a production pipeline.

## Decision

Load history once from those files (read-only). Only increments come from the source API.

## Consequences

This project depends on the research repo's files for the backfill only; afterwards it is independent.
