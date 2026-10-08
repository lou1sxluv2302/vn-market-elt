# ADR-0004: BigQuery as the primary warehouse

- Status: Accepted
- Date: 2026-10-06
- Spec: D4

## Context

Options were BigQuery, Snowflake, AWS Athena/Redshift and Databricks. Only BigQuery has a perpetual free tier (storage and queries), and it matches the owner's day-job stack.

## Decision

BigQuery is primary. Snowflake, Athena and Databricks are comparison phases after the cold path is stable.

## Consequences

Free-tier limits (storage, bytes scanned) become design constraints: partition by date, avoid auto-refresh.
