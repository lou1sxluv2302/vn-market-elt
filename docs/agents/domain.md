# Domain docs

How the engineering skills consume this repo's domain documentation.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root: the project's language (single context).
- **`docs/adr/`**: decisions; read the ones touching the area you work in.
- **`docs/domain.md`**: routes market-knowledge questions to `docs/knowledge/`.

## Layout

Single-context: one `CONTEXT.md` at the root and `docs/adr/`. Glossary entries carry
a definition, the code name, the Vietnamese term and words to avoid.

## Use the glossary's vocabulary

Name domain concepts exactly as `CONTEXT.md` does, in issue titles, tests, models and
columns. A missing term is a gap to close with `/domain-modeling` before use.

## Flag ADR conflicts

If output contradicts an ADR, say so explicitly, for example:
_Contradicts ADR-0011 (dbt views for the hot path) - but worth reopening because..._
