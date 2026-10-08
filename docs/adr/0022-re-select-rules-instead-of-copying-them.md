# ADR-0022: Re-select rules instead of copying them

- Status: Accepted
- Date: 2026-10-08
- Spec: D22

## Context

v1 accumulated 32 operating rules, many fitted to its own architecture (a
single DuckDB file, Windows Task Scheduler, a fixed rebuild order). Carrying
them over would constrain v2 without protecting it.

## Decision

A rule enters v2 only if it (1) prevents irreversible harm, (2) is standard
industry practice, or (3) can be enforced by a tool. Tool-enforced rules are
preferred. Rules are written as defaults with a stated escape; only the
always-on guardrails in `CLAUDE.md` are absolute.

## Consequences

`docs/engineering-rules.md` is reviewed against these criteria during K0.1.
