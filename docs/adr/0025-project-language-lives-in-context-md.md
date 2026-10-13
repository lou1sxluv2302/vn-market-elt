# ADR-0025: The project's language lives in CONTEXT.md

- Status: Accepted
- Date: 2026-10-13
- Supersedes: ADR-0015
- Spec: D15

## Context

ADR-0015 made `docs/glossary.md` the single source for naming Vietnamese market
terms. The engineering skills adopted from mattpocock/skills (`domain-modeling`,
`grill-with-docs`, `code-review`) read the project's language from `CONTEXT.md`
at the repository root. Keeping both files would give one concept two homes.

## Decision

`CONTEXT.md` at the repository root is the single source of the project's
language, in that format: a definition of what each term is, its code name, its
Vietnamese term and the words to avoid. `docs/glossary.md` is removed. A term is
added to `CONTEXT.md` before it appears in prose, issues, tests or code.

## Consequences

Behaviour and rules about a term (dates, limits, procedures) stay in
`docs/knowledge/`; `CONTEXT.md` holds definitions only.
