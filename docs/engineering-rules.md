# Engineering rules

The single source for how code in this repository is written, verified and run.
Each rule was paid for by an incident in the research repo ("v1") this project grew
out of; the date and number are given so the rule can be argued with, not just obeyed.

**Policy (D22, ADR-0022).** A rule is here only if it prevents irreversible harm, is standard practice, or a tool enforces it.
Every rule is a default with an escape; the absolute guardrails are the four "Always on" items in [`CLAUDE.md`](../CLAUDE.md).

**Recording an escape.** Note it next to the bypass (`# noqa: <code> - <reason>`, a dbt `meta.reason`, or a flag that logs
its reason) and under **Deviations** in the PR description. Tools named below land in the phase that needs them (spec §6).

Data-content lessons (units, adjusted vs raw prices, truncating sources, stale sessions) live in
[`knowledge/data-quality-lessons.md`](knowledge/data-quality-lessons.md). Secrets and logging: [spec §14.4-14.5](spec.md#14-security).

## Verification

- **Every script that computes or transforms ships `--self-test`: offline, synthetic data, a known answer.**\
  Why: v1 2026-08-05: six measurement bugs in one session, each producing a plausible wrong conclusion until run on a known answer.\
  Enforced by: CI `ci / self-test` discovers and runs every `--self-test`. Escape: a thin I/O wrapper with no logic is listed in the job's exemption list with a reason.
- **Results have three states - ✅ passed · 🔴 failed · ⚪ not run - and only ✅ counts as passed.**\
  Why: v1 2026-08-07: a check silently switched itself off past 25 rules; its ⚪ line was the only alarm, while its self-test stayed green.\
  Enforced by: CI fails when a required step is skipped; every dbt model with tests also has a non-empty test. Escape: a check that cannot apply by design reports ⚪ with its reason.
- **Exit codes decide; printed text explains.**\
  Why: v1 2026-08-05: an aggregator parsed output text and painted 🔴 on three scripts that exited 0 and six that only lacked a library.\
  Enforced by: GitHub Actions step status; `tools/gate.py` reads exit codes only. Escape: a tool that cannot signal by exit code gets a wrapper that translates.
- **Every test ships a planted fault that carries the real failure mechanism and turns exactly that test red.**\
  Why: v1 2026-08-07: a planted fault (`stop = 2 × entry`) passed all 4 gates because the evidence table had 0 checks.\
  Enforced by: self-tests assert each fault fails its target test and no other; P3 is done when every test has failed at least once. Escape: dbt's built-in generic tests rely on dbt's own test suite.
- **One assertion per test.**\
  Why: v1 2026-08-05: DQ test 50 merged two conditions into 667 violations; splitting showed 667 + 0, one fixable and one not.\
  Enforced by: dbt generic tests are single-assertion by construction; review for singular tests. Escape: a composite test whose conditions share one fix names both in its description.
- **Reconcile every new path against a known answer: per-batch counts, and the v1 DuckDB opened read-only.**\
  Why: v1 2026-08-03: silver stood still at 2026-03-27 while bronze advanced and 54/54 validations passed - internal consistency is not cross-layer agreement.\
  Enforced by: `tools/reconcile_duckdb.py` and dbt cross-layer count tests (S2, P1-P4 done-when). Escape: a mismatch caused by a known v1 defect is recorded with its cause in the reconcile report; tolerances stay as measured.

## Boundaries and outbound calls

- **Every outbound call has a timeout, nested socket ⊂ call ⊂ step, each inner limit strictly shorter than its outer one.**\
  Why: v1 2026-08-14: a step hung ~3 h with no timeout and no gate fired; 2026-09-22: step and scheduler limits were both 4 h, a race that loses logs.\
  Enforced by: timeout keys in `config/*.yml`; self-tests plant a hang and assert each layer fires first. Escape: none for the layer; values change in config with a measurement in the PR.
- **Size each timeout from the measured duration of the first call, not the median.**\
  Why: v1 2026-08-16: the first call took 19.57 s (authentication), later ones ~0.25 s; a median-based limit would have killed every run at its first call.\
  Enforced by: convention; the measurement goes in the config comment. Escape: an unmeasured call starts at the library default plus a note to measure.
- **On timeout, kill the whole process tree.**\
  Why: v1 2026-08-14: `subprocess.run(timeout=)` killed only the direct child; a grandchild held the pipe open and the wait went on.\
  Enforced by: one helper in `vnmarket.common` with a self-test that spawns a grandchild. Escape: an in-process call with no children needs only the call-level limit.
- **For a stream, the step timeout is the stall threshold `stale_alert_minutes` in `config/collector.yml`.**\
  Why: a stalled WebSocket raises no error; the v1 2026-08-14 hang had the same shape - silence, not failure.\
  Enforced by: `healthcheck.py`; S1 planted fault (cut the VM's network 5 min ⇒ the e-mail arrives). Escape: change the value in config, citing the S0 message rate.

## Loads and sources

- **Assert row counts after every load; a script's success message is not evidence.**\
  Why: v1 2026-04-08: a load reported success while no VN-Index rows were inserted.\
  Enforced by: dlt load info compared with source counts per batch; dbt row-count tests per partition. Escape: a genuinely empty day is declared by the calendar seed, never by lowering the bound.
- **Raw is append-only and verbatim; parsing and cleaning happen in dbt.**\
  Why: v1 never stored a raw price (`close_raw` 100 % NULL), so its adjusted prices could never be verified (closed as a permanent limit 2026-08-19).\
  Enforced by: `sa-collector` holds `objectCreator` only; the raw bucket has no deletion lifecycle; dlt `write_disposition="append"`. Escape: restatements are appended and the latest wins downstream.
- **One primary source per dataset; a second source only cross-checks.**\
  Why: v1 2026-08-06: legacy history spliced to a newer vendor's tail made a false price jump at the splice in 42 % of symbols.\
  Enforced by: dbt `accepted_values` on `_source_id` per dataset. Escape: changing the primary source is a new ADR plus a full reload, never a splice.
- **Measure coverage on every load and block the write when it falls short; thresholds are ratios, not counts.**\
  Why: v1 (before 2026-08-04): a source silently returned its latest 100 rows - 400 of 2,891 sessions (13.8 %), every column 100 % non-null.\
  Enforced by: dbt coverage test against the trading calendar; a tripwire on round row counts (exactly 100 or 1,000). Escape: a known-partial source loads with its measured coverage set as the threshold in config.
- **Checksum every transfer: crc32c on every GCS upload.**\
  Why: v1 2026-08-04: a mount served a stale 41,433 B copy of a 45,248 B file, which nearly overwrote newer work.\
  Enforced by: `uploader.py` uploads with `checksum="crc32c"`; its self-test plants a corrupted byte. Escape: copies within one local filesystem.
- **Every raw row carries `_source_id` and `_ingested_at`, tested `not_null`.**\
  Why: v1 2026-08-06: the source column is what let a test block 290 spliced rows by vendor; without it the splice was invisible.\
  Enforced by: dbt `not_null` on both columns in every source. Escape: none needed; a source without a natural id uses its loader's name.
- **Loads are idempotent per partition; backfill and daily runs use the same code.**\
  Why: v1 2026-08-07: a one-off loader was "idempotent" by deleting and rebuilding the store - safe on day one, it later erased 44,878,963 rows.\
  Enforced by: self-tests load the same partition twice and compare counts. Escape: a one-time migration is dry-run by default and removed after use.

## dbt modelling

- **Declare every model's grain and test it with `unique` and `not_null`.**\
  Why: v1 2026-08-16: `CREATE OR REPLACE` silently dropped primary keys; declared constraints are not enforced, and BigQuery does not enforce them either.\
  Enforced by: dbt tests; a CI check that every model has a `unique` test. Escape: a single-row model states "grain: one row" in its description.
- **Select columns by name and build lineage with `ref()` and `source()`; avoid `SELECT *`.**\
  Why: v1 2026-08-05: `SELECT i.*` carried a stale `exchange` over the corrected one - 260,054 rows (21.9 %) on the wrong exchange.\
  Enforced by: sqlfluff `AM04`; dbt lineage shows every copy to trace after a fix. Escape: `SELECT *` from a CTE whose columns are listed above it.
- **Point in time: a row for date D uses only information published by D; rolling windows end at the previous row.**\
  Why: v1 06a §v1.6.8: the source's market cap used a price ~105 days after period end - look-ahead; v1 recomputed it from stored prices.\
  Enforced by: a truncation test - recompute with data after D removed and assert equal values. Escape: a reconciliation model may look ahead and says so in its name.
- **Keep delisted symbols and bad periods; flag them instead of deleting.**\
  Why: v1: dropping delisted symbols is survivorship bias; stale sessions (32.5 % of rows) are flagged `is_stale` and excluded from calculations.\
  Enforced by: a dbt test that marts keep every symbol present in staging. Escape: exclusion happens in a filter on the flag, downstream.
- **Derived flags are three-valued: NULL means "cannot be assessed", FALSE means "assessed and no".**\
  Why: v1 module 04 §7.6b: FALSE on sessions before share data existed made every one of them look checked; warm-up rows need NULL, not 0.\
  Enforced by: a dbt test that rows without enough history hold NULL. Escape: a flag that is assessable on every row documents that.
- **A test blocks downstream only when a rerun can fix what it found.**\
  Why: v1 2026-09-11→21: a blocker on an unfixable past gap stopped the chain six runs in a row, losing six sessions forever.\
  Enforced by: dbt `severity: error` for fixable data faults, `warn` for past gaps, both shown in the gate report. Escape: the owner raises a `warn` to `error` for one run, recorded in the PR.
- **Seeds carry `as_of`; a test fails when market rules are over 90 days old or next year's holidays are missing.**\
  Why: v1 relied on a calendar note ("review quarterly, holidays every December") that nothing checked.\
  Enforced by: dbt tests on the seeds. Escape: no calendar row for today ⇒ the collector runs anyway (spec S1); the test warns.

## Command-line tools

- **Every CLI lists its valid arguments and exits non-zero on anything else.**\
  Why: v1 2026-08-07: a script swallowed an unknown argument and ran straight into `unlink()`, deleting the 2.02 GB store.\
  Enforced by: `argparse` (exit 2 by default); each self-test passes a bogus argument and expects it. Escape: a forwarding wrapper may use `parse_known_args` and passes the rest on unchanged.
- **Writes are dry runs by default; `--apply` performs them.**\
  Why: v1 2026-08-07: the delete above needed no `--apply` and no confirmation.\
  Enforced by: `argparse` default plus a self-test that the default writes nothing. Escape: the scheduled production unit passes `--apply` explicitly.
- **Sample, smoke and test runs default to temporary paths and `dev_*` datasets.**\
  Why: v1 2026-08-21: a smoke test's `finally` block unlinked the real store (1.93 GB) and 373 frozen log rows were lost forever.\
  Enforced by: defaults in config; self-tests assert the default target is not production. Escape: `--target prod --apply`, both explicit.

## Storage and recovery

- **Back up irreplaceable data first: outside the store, before each load, kept 2× the detection time, restore-drilled.**\
  Why: v1 2026-08-07: backup tables inside the same file died with it; 2026-08-14: a silent loss took a week to notice, so 7-day copies were all corrupted.\
  Enforced by: GCS object versioning on the raw bucket (Terraform); a restore drill in `docs/runbooks/`. BigQuery time travel (7 days) is not a backup. Escape: a table rebuildable from raw by `dbt build` needs no snapshot; the runbook says so.
- **Deletion rights live in IAM: pipeline identities create; only the owner deletes.**\
  Why: v1 2026-08-07 and 2026-08-21: both store losses came from code paths that could delete what they were meant to read.\
  Enforced by: resource-scoped roles in spec §14.2 (Terraform). Escape: the owner deletes by hand after an export, noted in the PR.

## Change discipline

- **Constants live in `config/*.yml` (Python) and dbt seeds or vars (SQL).**\
  Why: v1: two components used different flag names for one parameter and their settings drifted silently.\
  Enforced by: review; a CI lint for inline thresholds. Escape: a self-test's own thresholds live with the self-test.
- **A name equals the expression that produces it.**\
  Why: v1 2026-08-05: `stop_method` compared rounded with unrounded values and labelled 494 of 667 rows `atr` when Kijun decided them.\
  Enforced by: convention; dbt column descriptions state the formula. Escape: a legacy name kept for compatibility documents its true expression.
- **A rule that lives only in a comment becomes code.**\
  Why: v1 2026-08-06 (07 §v2.7.5): the rule that chose the operating configuration existed only as a YAML comment, so the choice was asserted, not derived.\
  Enforced by: convention; the code that applies it stops when the result differs from what is declared. Escape: a comment explaining why a value was chosen stays a comment.
- **Numbers written in docs or comments are re-measured by a test.**\
  Why: v1 2026-08-26: three recorded contrast ratios re-measured as 15.41, 5.88 and 4.89 instead of 14.26, 5.93 and 4.94; no check compared them.\
  Enforced by: a test that recomputes each documented number. Escape: a number labelled "measured on v1, <date>" (D21) is history, not a claim about v2.
