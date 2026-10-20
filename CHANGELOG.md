# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) as described in `CONTRIBUTING.md`.

## [Unreleased]

### Added
- `vnmarket.el.load_vci_reference`: Vietcap REST without the vendor library (PyPI
  quarantined vnstock / vnai). It loads two raw tables:
  - corporate actions (dividends and share issues from 2000, every page), refused on a
    silent truncation or a shrinking history;
  - a daily VN30 / HNX30 membership ledger.

  dbt: `stg_vci__corporate_actions`, `stg_vci__index_membership`, `fct_corporate_action`
  (typed) and `fct_index_membership_daily` (inclusion flag). Two unit tests; 3 new planted
  faults and 1 extended.
- Financial statements from v1's file: `load_v1_history --datasets fundamentals` loads the
  statements and the charter-capital history as snapshots, clustered by symbol.
  `stg_vnstock__fundamental_statement`, `int_fundamentals__quarterly` and
  `fct_fundamental_quarterly` provide quarterly revenue, parent profit, derived operating
  cash flow, ROE and shares, each with the date and the first session a quarter may be used.
  The seed `fundamental_availability` holds the statutory deadline + 5 days, reconciled with
  v1's date on every row. One unit test; 4 new planted faults, and 2 existing faults extended.
- `dim_symbol` (current exchange and ICB industry / supersector in Vietnamese and English,
  from the newest snapshot; today's classification, not point in time) with staging
  `stg_vnstock__symbol_industries` and `stg_vnstock__industries_icb`;
  `dim_trading_calendar.trading_month_label` ("2026-01") for the report's month filter.
- BI marts for the end-of-day report: `int_prices__indicators` (return against the previous
  close; SMA 20 / 50 / 200 and 52-week high / low over non-stale sessions, NULL in warm-up),
  `fct_symbol_session_daily`, `fct_market_breadth_daily` (flows.md §4 counts; no ceiling /
  floor on adjusted prices), `fct_market_flow_daily`, `fct_universe_summary_daily`,
  `dim_trading_period` (`session_count`, `is_period_complete`); `fct_build_status` written
  by an `on-run-end` hook after each prod invocation; `tools/build_pbi_theme.py` (Power BI
  theme from `config/palette.yml`); runbook `bi-report.md`. Unit tests with exact answers;
  recount tests and planted faults for look-ahead, stale rows and survivorship.
- S0 local probe report (#32): `docs/reports/s0-feed-probe.md` - 30 minutes of a live
  session, aggregates only; the gate's inputs and the sizing for Q6.
- S1.4 stale-feed alert (#41): the uploader writes one point of a custom metric per
  loaded batch; a PromQL alert policy e-mails when none arrives for 3 minutes inside a
  trading window (windows in `config/collector.yml`, confirmed holidays from the seed),
  tried on the live metric with a control and planted cases. ADR-0032.
- S2 load (#38): the uploader appends each batch to `raw_vps_stream.messages` from the
  file it verified against GCS, exactly once by job id, and deletes it only when the job's
  rows equal the file's; objects carry their message count; `tools/reconcile_stream.py`
  compares GCS and BigQuery per batch. Terraform: the table, and the owner may impersonate
  `sa-collector`. ADR-0031.
- S1 collector code (#36): `stream_collector.py` writes every feed message verbatim to
  one parquet file per 60-second window in a local spool (atomic, restart-safe names,
  back-off reconnects, confirmed holidays skipped); `uploader.py` moves the spool to the raw
  bucket and deletes a file only when the stored object's size and CRC32C match. Extra
  `collector`. ADR-0030 (the stale-feed alert comes from Cloud Monitoring).
- P4 (#34): `fct_price_revision` classes every vendor history rewrite (same_close,
  rescale, noise, other; thresholds measured on prod) with unit tests, two planted faults
  and a warning on `other` above the measured count; `reconcile_v1_marts.py --log` appends
  a daily result and `--streak` counts consecutive passing sessions. ADR-0029.
- S0 feed probe (#32): `src/vnmarket/collector/feed_probe.py` records every feed message
  verbatim with `received_at`, connection events and RAM/CPU, under time limits, by path
  under the interpreter that holds the licensed feed library; `feed_report.py` aggregates
  a run (counts, sizes, field names per type, no values). Runbook `s0-feed-probe.md`.

### Fixed
- `fct_price_daily`'s tick rank breaks a tie by source (primary first), so a key that
  reaches it twice no longer keeps a row chosen by row order; the planted fault
  `both_sources_kept` was red on Windows and green on Linux because of it (#42). Prod has
  one row per key: its output is unchanged.

## [0.2.0] - 2026-10-16

Cold path: v1's daily history on BigQuery, dbt marts reconciled against v1, 66 data
tests each proven able to fail. Tagged on `3e3a274` (#31) on 2026-10-17.

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
- README for the cold path: lineage diagram, what is built and how it is verified (#31).

### Measurements
- `tools/reconcile_v1.py`: 4/4 checks - raw equals v1's parquet per file (145 files,
  12,339,172 OHLCV rows to 2026-10-13); latest-wins reproduces v1 except residuals at
  their measured counts; reference lists equal.
- `tools/reconcile_v1_marts.py`: 4/4 checks, every difference named by its mechanism
  (2026-10-16: 949,799 price rows equal row by row on the 261 symbols whose signatures
  differ, 7,966 source_choice, 179 fallback_batch_not_in_log, 26
  dropped_after_neighbour_source_change, 4 stale_from_neighbour; 1,287 symbols identical
  by signature).
- `tools/planted_faults.py`: the control passes every data test; each planted fault
  turns red exactly the tests it names; no data test is never red.
- `dbt build --target prod`: green, 136 nodes (2026-10-16).

## [0.1.0] - 2026-10-13

Foundations: a public repository with baseline security, CI as required checks, and
the Google Cloud foundation in Terraform; knowledge harvested from v1. Tagged on
`0104eba` (#15) on 2026-10-17.

### Added
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

### Measurements
- A pull request with a red check was blocked by `protect-main`; gitleaks caught a
  planted key in a throwaway repository (#9).
- Terraform: `bootstrap` 13 and `main` 46 resources applied by the owner;
  `infra / terraform-plan` green through WIF.
- Security audit before the first push (2026-10-13): no secret in any git object.
