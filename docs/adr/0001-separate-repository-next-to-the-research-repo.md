# ADR-0001: Separate repository next to the research repo

- Status: Accepted
- Date: 2026-10-06
- Spec: D1

## Context

The research repository runs a scheduled 15:00 pipeline on whatever branch is checked out, and forbids extra worktrees. A repository nested inside it would be swallowed as a gitlink by `git add -A` and would pollute every search.

## Decision

Use a separate repository in a sibling folder.

## Consequences

The two projects share nothing but read-only access to the research repo's parquet files and DuckDB.
