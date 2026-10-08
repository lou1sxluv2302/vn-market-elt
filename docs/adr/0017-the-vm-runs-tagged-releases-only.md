# ADR-0017: The VM runs tagged releases only

- Status: Accepted
- Date: 2026-10-06
- Spec: D17

## Context

Running `main` HEAD makes it impossible to say what is in production.

## Decision

`infra/deploy.sh <tag>` checks out exactly one tag on the VM.

## Consequences

Rollback is deploying the previous tag.
