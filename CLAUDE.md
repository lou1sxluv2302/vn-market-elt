# CLAUDE.md — router

This file **routes**; it holds no knowledge. Find the topic, open the file,
follow it. The owner speaks **Vietnamese**; everything written **into the
repository** is **English** (ADR-0014).

## Route by topic

| Topic | Open |
|---|---|
| **Scope** — goals, phases, latency budget, what is in or out | `docs/spec.md` |
| **Decisions** — why something is the way it is; changing one means a new ADR | `docs/adr/README.md` |
| **Progress** — what is done, what is next | `docs/spec.md` §0 until GitHub milestones exist; then `gh issue list --milestone "<phase>"` and `CHANGELOG.md` |
| **Engineering** — self-tests, timeouts, config, CLI, logging, data invariants | `docs/engineering-rules.md` |
| **Research** — stock selection | Not in this repository: a **private** companion repo (location in `CLAUDE.local.md`) |
| **Domain** — sessions, price bands, ex-rights, sources, the VPS feed, vnstock licences | `docs/domain.md` |
| **Naming** — a Vietnamese market term in code | `docs/glossary.md`; columns, models, resources in `docs/spec.md` §13 |
| **Security** — identities, secrets, network, threat model, audits | `docs/spec.md` §14; audit procedure `docs/runbooks/security-audit.md`; reporting policy `SECURITY.md` |
| **Git** — branches, commits, PRs, tags, releases | `CONTRIBUTING.md` |
| **Infrastructure** — Terraform, VM, deploy | `infra/CLAUDE.md` (loads when working in `infra/`) |
| **Constants** — thresholds, intervals, schedules | `config/*.yml` |

Directory-specific rules live in a `CLAUDE.md` inside that directory and load
only when you work there.

## Always on

These hold in every task, because breaking them cannot be undone.

1. **The repository is public.** Commit code, docs and **synthetic** fixtures
   only; research hypotheses, features and results live in the private repo;
   market data, keys, tokens, project ids and e-mail addresses stay out
   (`.gitignore` and gitleaks enforce it; `SECURITY.md` explains why).
2. **Keyless cloud access** — attached service accounts, ADC, or WIF (ADR-0012).
3. **The earlier research repo (v1) is read-only** from here (local paths are in
   `CLAUDE.local.md`, which is git-ignored);
   its DuckDB opens with `read_only=True`.
4. **Pushes, PRs, tags and `terraform apply` wait for the owner's go-ahead** in
   the conversation.

## Keeping this file a router

New knowledge goes into the topic file it belongs to, and this table gains at
most one row. Target ≤ 80 lines; hard limit 200.
