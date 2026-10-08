# ADR-0021: Inherit v1 knowledge through a reviewed harvest

- Status: Accepted
- Date: 2026-10-08
- Spec: D21

## Context

The research repository (v1) holds about 10,000 lines of Vietnamese knowledge
base: market microstructure, data-source behaviour, and lessons from real
incidents. It also has infrastructure and data-model errors. Pointing at it
keeps v2 dependent on v1; copying it wholesale imports its errors.

## Decision

Run phase K0: inventory every section with a label (KEEP, LESSON, V1-RULE,
STALE, RESEARCH), have the owner approve the inventory, then translate and
condense. After migration, `docs/knowledge/` is v2's source of truth (the inventory itself is kept
in the private research repository); v1 is a
frozen reference.

## Consequences

The two copies may diverge by design. Facts keep their evidence level and v1
source; numbers measured on v1's warehouse are labelled as such.
