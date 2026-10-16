# ADR-0029: P4 - increments from v1's parquet for now; vendor rewrites classified, not blocked

- Status: Accepted
- Date: 2026-10-16
- Spec: P4, Q1 (amends ADR-0002)

## Context

ADR-0002 planned to load history once from v1's parquet and take only increments from the
source API. Since P1 a daily job on the owner's machine (after v1's 15:00-16:00 write
window) reloads v1's new parquet files; dlt state loads only what is new. Pulling from the
vendor API directly would share v1's API key and device licence with v1's own daily job.

The vendor rewrites history. Measured on raw 2026-10-16 (47 pulls of the primary source
since 2026-08-03): 593,237 keys of 219 symbols changed between pulls; grouped by (source,
symbol, pull), 1,357 rewrites. Staging keeps the newest pull, so the marts were right, but
nothing counted or classified the rewrites.

## Decision

1. Increments keep coming from v1's parquet until the owner decides otherwise (owner,
   2026-10-16). ADR-0002's "only increments come from the source API" is deferred, not
   dropped.
2. `fct_price_revision` keeps one row per rewrite with a class, checked in order:
   `same_close` (no close changed: a session's volume, high or low restated), `rescale`
   (every close up to the last changed date lies within rounding - 20 VND, two steps of the
   vendor's 10-VND grid - of one ratio, and at least 99% of those rows changed: a corporate
   action re-adjusted), `noise` (every changed close moved by at most 0.5%), `other`.
   Measured: 970 same_close, 357 rescale, 8 noise, 10 other.
3. `other` **warns** above the measured count (10); it never blocks the build. A rewrite is
   a fact about the source, not a fault in the data, and staging already keeps the newest
   pull.
4. No incremental dbt models yet: the full prod build takes ~4 minutes inside the free
   tier, and with rewrites every day an incremental model would rebuild most of the
   rewritten symbols' history anyway. Revisit at S2, where the hot path needs them.
5. `tools/reconcile_v1_marts.py` runs daily after the build and appends its result to a log
   (`--log`); `--streak` counts consecutive passing sessions. P4 is done at 10.

## Consequences

- v2 stays dependent on v1's daily files; if v1 stops, v2 stops with it. The reconciliation
  log shows that the same day.
- Deviation is measured on every row up to the last changed date, changed or not: a row the
  vendor left out of a rescale (D11, AGG and ADP each had one) lands in `other`; checked
  only on changed rows, the three passed as rescales.
- A new kind of rewrite raises a warning to read, not a red build.
