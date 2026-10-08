# ADR-0019: Public repository from day one

- Status: Accepted
- Date: 2026-10-06
- Spec: D19

## Context

GitHub Free offers branch rulesets only on public repositories. A public history from the first day is also part of the demo.

## Decision

The repository is public from the start.

## Consequences

Leak prevention runs on every PR (gitleaks, data-file block, push protection), not as a one-off review before going public.
