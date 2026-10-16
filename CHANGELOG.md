# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) as described in `CONTRIBUTING.md`.

## [Unreleased]

### Added
- `load_v1_history --datasets` loads a chosen subset (default: all; unknown names refused)
  and counts only what it loaded; `tools/prune_flow_snapshots.py` (dry run by default)
  removes flow snapshots older than the newest, the one exception to append-only raw (#29).
- Flow and index marts (#26): `fct_foreign_flow_daily`, `fct_prop_flow_daily` (totals
  always; the match / put-through split only where match + put-through = total on every
  side and unit, and for foreign flow from 2020-01-02; `prop_data_available`) and
  `fct_index_daily` (index points). Macro `null_invalid_flow_split` (net derived as buy minus sell), generic tests
  `breakdown_identity_holds` and `split_null_when_invalid`, a known-answer unit test,
  planted faults for every new test. Terraform: dataset `marts_research` and
  `dev_marts_research` for the research project.
- Flows and index history (#26): `load_v1_history` loads v1's daily foreign and proprietary
  flow files as content-hashed snapshots (partitioned and clustered like OHLCV) and v1's
  index table, read read-only from its DuckDB, as a snapshot; after every run each current
  snapshot is counted in the destination. Staging `stg_vnstock__foreign_trade`,
  `stg_vnstock__prop_trade`, `stg_vnstock__index_daily` (newest snapshot; integer VND and
  shares by trade type; index points). `tools/reconcile_v1.py` compares each newest
  snapshot with v1 by content hash and per-symbol signatures. Planted faults cover the new
  staging tests.
- Data-quality tests (P3, #23): v1's checks for the layers v2 has, one condition each - price
  structure (close positive, close and open within the day's range, volume, multiple of
  10 VND), trading days and `session_seq`, ADV window and no look-ahead, no stale row in
  the universe, watched symbols complete, marts not behind raw, last session not sparse,
  exchange per period and from the symbol list, fallback only without a clean primary,
  calendar without gaps, seeded holidays or weekend sessions, universe in falling markets,
  `not_empty` on every guarded model. Past-gap checks (watched symbols, falling markets)
  and the fallback-rows monitor (ceiling 151, measured on prod) warn instead of blocking.
- `tools/planted_faults.py`: a synthetic DuckDB warehouse; the control passes every data
  test and each of 32 planted faults turns red exactly the tests it names; any data test
  never red fails the run. Runs in `ci / dbt-test`; step limit in `config/dq.yml`.
- `vnmarket.common.process`: `run_bounded` kills the whole process tree on timeout
  (engineering-rules); `tools/run_self_tests.py` and the fault matrix use it.
- dbt marts (P2 part 2, #20, ADR-0028): `dim_trading_calendar` (observed history, weekdays
  minus seeded holidays after it, sessions per month), `dim_security` (SCD2 exchange; the
  HNX→HOSE move; tick-inferred exchange for delisted symbols, flagged),
  `fct_price_daily` (v1's drop rules; exchange, tick and band of the trade date),
  `fct_liquidity_daily` (ADV20 over previous non-stale rows, provisional tiers),
  `fct_universe_daily` (flag and first exclusion reason). Portable date macros; six new
  unit tests, every mutant of the key rules caught.
- `tools/reconcile_v1_marts.py`: marts against v1, every difference explained row by row
  by its mechanism (holiday seed, source choice and its effect on `is_stale` and ADV
  windows, inferred exchange); anything else fails. Reads marts as `sa-bi-reader`.
- `tools/check_seeds_vs_knowledge.py`: tick sizes, normal bands and holidays in the seeds
  agree with `market-microstructure.md`; run in `ci / lint`.
- Source choice prefers a clean row: the primary's, else the fallback's, else the primary's
  broken one (found by reconciliation: GMX 2013-11-22, primary close below its low, was lost
  while the fallback row was clean). The bad-row checks live in one macro.
  Cost, measured: 26 primary rows of 11 symbols (2019-2021) that v1 kept as stale are
  dropped, because the clean fallback day before makes them non-stale with the open
  outside [low, high]; the reconciler names this `dropped_after_neighbour_source_change`.
- dbt project (P2 part 1, #20): market-rule seeds with effective dates and sources
  (tick size, price band, holidays incl. 2026-11-24 and provisional 2027, exchange
  aliases, the HNX→HOSE move, known bad dates); staging latest-wins over the raw log;
  primary-first source choice; `is_stale` and v1's bad-row flags. dbt runs as `sa-dbt`
  by impersonation; dev datasets expire tables after 7 days. CI job `dbt-test` runs
  seed tests and unit tests on DuckDB, no warehouse.
- P1 history load (#18): `vnmarket.el.load_v1_history` (dlt, append-only, every pull
  kept with file lineage; v1's schema checked before loading, types frozen; reference
  lists as content-hashed snapshots; backups never read; rows counted after the load;
  dry run by default) and `tools/reconcile_v1.py` (raw = parquet per file with a
  date-weighted checksum, latest-wins reproduces v1 with residuals capped at their
  measured counts, reference lists, v1 untouched); self-tests on a seeded synthetic
  bronze tree (`tests/fixtures/synthetic_bronze.py`) with a local DuckDB destination.
  Runbook `docs/runbooks/p1-history-load.md`.
- `sa-loader`: writes `raw_vnstock` only; the owner reaches it by impersonation, no key.
- Terraform (#14, ADR-0027): `bootstrap` stack (APIs, versioned state bucket) and
  `main` stack (raw bucket, 6 datasets, 4 service accounts with resource-scoped IAM,
  WIF for GitHub Actions pinned to the repository id, `vnstock-api-key` container,
  security alerts; collector VM in its own VPC behind `create_vm`).
- `infra` workflow: `terraform-validate`, and `terraform-plan` through WIF that
  prints only a change count, with every environment value in masked secrets.
  Dependabot watches the Terraform providers.
- Knowledge K0.3 (#12): `indicators.md`, `flows.md`, `bi-conventions.md`; 26 new
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

