# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) as described in `CONTRIBUTING.md`.

## [Unreleased]

### Added
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
