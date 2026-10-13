# ADR-0015: One glossary for Vietnamese market terms

- Status: Accepted · amended 2026-10-13: the glossary is `CONTEXT.md` at the repo root
- Date: 2026-10-06
- Spec: D15

## Context

Two English names for one concept cannot be reconciled by any check.

## Decision

`CONTEXT.md` at the repo root is the single source (moved from `docs/glossary.md` so the engineering skills from mattpocock/skills read it natively); a term is added there before it appears in code.

## Consequences

Reviewers check new terms against the glossary in the PR checklist.
