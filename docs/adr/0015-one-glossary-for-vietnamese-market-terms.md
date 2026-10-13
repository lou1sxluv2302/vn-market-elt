# ADR-0015: One glossary for Vietnamese market terms

- Status: Superseded by [ADR-0025](0025-project-language-lives-in-context-md.md) (2026-10-13)
- Date: 2026-10-06
- Spec: D15

## Context

Two English names for one concept cannot be reconciled by any check.

## Decision

`docs/glossary.md` is the single source; a term is added there before it appears in code.

## Consequences

Reviewers check new terms against the glossary in the PR checklist.
