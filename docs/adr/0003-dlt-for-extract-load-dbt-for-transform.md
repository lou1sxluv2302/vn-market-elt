# ADR-0003: dlt for extract-load, dbt for transform

- Status: Accepted
- Date: 2026-10-06
- Spec: D3

## Context

The project exists to practise ELT. The research repo transforms in Python before loading.

## Decision

Use dlt for extract-load and dbt for all transformations.

## Consequences

Transformations are SQL with tests, docs and lineage, and run on any warehouse dbt supports.
