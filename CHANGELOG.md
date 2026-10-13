# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) as described in `CONTRIBUTING.md`.

## [Unreleased]

### Added
- Knowledge K0.3 (#12): `indicators.md`, `flows.md`, `bi-conventions.md`; 21 new
  terms in `CONTEXT.md`.
- A measured v2 palette (ADR-0026): `config/palette.yml` for light and dark themes,
  `tools/check_palette.py` (WCAG contrast, CIEDE2000 under simulated colour-vision
  deficiency, OKLCH chroma; self-tested against published values), run in CI; the
  research basis in `docs/design/colour-and-ux-research.md`.
- CI (#9): `ci` workflow (lint, self-test) and `security` workflow (gitleaks over
  full history, secret scan, data-file block, pip-audit; weekly run that also reports
  outdated hook releases). Actions pinned
  to commit SHAs, read-only permissions.
- `tools/run_self_tests.py` finds every `--self-test` with `ast` and runs it;
  `tools/check_pins.py` keeps tool versions equal across pyproject, hooks and workflows.
- pre-commit `check-yaml`: an unquoted `: ` in a step name made GitHub reject a
  whole workflow without running a single job.
- Agent workflow skills in `.claude/skills/`: `start-step`, `ship-pr`,
  `security-audit`, `release` (owner-invoked) and `harvest-knowledge` (#2).
- Engineering skills from mattpocock/skills wired in: `docs/agents/` configuration
  (GitHub Issues, default triage labels, single-context domain docs).
- Git guardrail hook for agents (Bash and PowerShell tools), with known-answer tests;
  runs without `jq`.
- GitHub project setup: pull request and issue templates, CODEOWNERS, labels,
  phase milestones (#7).
- Local setup instructions; pre-commit active (#6).
- Repository skeleton, English specification, 20 architecture decision records,
  glossary of Vietnamese market terms, engineering rules, domain router,
  contributing guide and security policy.
- `CLAUDE.md` as a topic router, with directory-scoped rules in `infra/CLAUDE.md`.
- Knowledge harvest from v1 (ADR-0021, ADR-0022): `market-microstructure.md`,
  `data-sources.md` and `data-quality-lessons.md` (45 lessons) translate the
  foundation.
- HNX→HOSE consolidation (2026-12-28), Vietnam Culture Day (24 November) and
  provisional 2027 holidays recorded in `market-microstructure.md`.
- `docs/engineering-rules.md` rewritten to 33 rules, each with its v1 incident,
  enforcement and escape.
- Glossary extended with 32 data-model terms.
- Security: `tools/secret_scan.py` (scans every git object, self-tested),
  pre-commit configuration, Dependabot, `.gitattributes`, wider `.gitignore`,
  pinned dependencies and the audit runbook `docs/runbooks/security-audit.md`.
- Spec v6: a stock-selection research track runs in a private companion
  repository (ADR-0023) under research discipline (ADR-0024); streaming is
  deferred behind it; tag plan re-mapped.

### Changed
- `CONTEXT.md` replaces `docs/glossary.md` as the project's language (ADR-0025
  supersedes ADR-0015).
- The ASCII hyphen is the only dash; a pre-commit hook rejects em and en dashes.
- ruff and pre-commit bumped (supersedes Dependabot #3, #4); hook revisions refreshed.
- The dash hook matches UTF-8 bytes (pygrep rejected `\N{...}` and crashed).
- `tools/secret_scan.py`: one git entry point, GitHub noreply addresses allowed by
  domain, self-test covers e-mail warnings.

