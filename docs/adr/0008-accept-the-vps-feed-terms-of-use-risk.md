# ADR-0008: Accept the VPS feed terms-of-use risk

- Status: Accepted
- Date: 2026-10-06
- Spec: D8

## Context

The feed belongs to VPS and is wrapped by vnstock; its terms of reuse are unclear.

## Decision

Accepted by the owner (2026-10-06). Data is never redistributed.

## Consequences

If the feed disappears, the hot path stops; the cold path is unaffected.
