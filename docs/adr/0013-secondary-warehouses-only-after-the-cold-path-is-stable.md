# ADR-0013: Secondary warehouses only after the cold path is stable

- Status: Accepted
- Date: 2026-10-06
- Spec: D13

## Context

Porting an unstable dbt project to four warehouses multiplies every fix by four.

## Decision

Snowflake, Athena and Databricks start after P3, reusing the same parquet and dbt project.

## Consequences

Warehouse-specific SQL goes behind macros from P2 on.
