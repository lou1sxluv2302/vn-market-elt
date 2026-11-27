# A five-minute tour

For someone who has five minutes with this repository: what problem it solves, how it is
built, one hard part in depth, and a fault caught on your own machine. Each step names the
file to open.

## 1. The problem (30 s)

Vietnamese market data is hard to keep correct over time:

- vendors deliver **adjusted** prices and silently rewrite whole histories after corporate
  actions;
- about a third of sessions are **stale** (volume 0, price copied; measured on the previous
  system, 2026-08), which turns indicators into divisions by zero;
- membership of the liquid universe, exchange moves and market rules change by date, so a
  model that reads today's values for an old date looks ahead without any error.

The goal is a warehouse where every number is **point in time** and every check has been
seen to fail. [Market microstructure](knowledge/market-microstructure.md) ·
[data-quality lessons](knowledge/data-quality-lessons.md).

## 2. The architecture (1 min)

Two paths into one BigQuery warehouse, transformed by one dbt project:

- **Cold path:** 26 years of daily history, loaded once by dlt into append-only raw tables,
  then rebuilt by dbt (staging → intermediate → marts). Built and verified (`v0.2.0`).
- **Hot path:** the intraday feed, written as 60-second parquet batches on an e2-micro VM,
  uploaded with a checksum check and loaded exactly once. Written and tested; not deployed.

Pictures: the [architecture diagram](../README.md#architecture) and the
[dbt lineage](lineage.md) (the number in each box is its data tests).
Decisions behind them: [the ADRs](adr/README.md). The dashboard, on synthetic data:
[overview](images/dashboard-overview.png) · [breadth](images/dashboard-breadth-dark.webp) · [flows](images/dashboard-flows.webp) ·
[flows by sector](images/dashboard-flows-by-sector.webp) · [sectors](images/dashboard-sectors-calendar.png).

## 3. One hard part: reconciling by mechanism, not by tolerance (1.5 min)

The warehouse replaces an earlier private system. "Matches within 0.1 %" hides real bugs, so
every difference between the two is named by the mechanism that produces it - a seeded
holiday the old calendar lacked, a fallback source chosen only when the primary row is not
clean, an exchange taken from the date's period instead of today's - and counted. A
difference with no name fails the check.

- Decision: [ADR-0028](adr/0028-p2-reconciliation-and-provisional-thresholds.md)
- Vendor rewrites classified instead of blocked: [ADR-0029](adr/0029-increments-from-v1-parquet-and-vendor-rewrites-classified.md)
- Code: `tools/reconcile_v1_marts.py`

## 4. A fault, caught on your machine (1 min)

No cloud account needed: the dbt project builds on DuckDB from a generated synthetic
warehouse.

```bash
pip install -e ".[dbt]"
python tools/planted_faults.py --fault adv_reads_current_row
```

The fault shifts the 20-session liquidity window onto the current session - the classic
look-ahead. The control build is green; with the fault, `assert_adv_excludes_current_row`
turns red. `--list` shows every fault. CI runs every one of them on each pull request and
fails if any data test is never red (`tools/planted_faults.py`, docstring).

## 5. Security and cost (30 s)

- **No service-account key exists anywhere:** attached identities on the VM, Workload
  Identity Federation in CI, impersonation for people, SSH only through IAP
  ([ADR-0012](adr/0012-no-json-service-account-keys-anywhere.md)).
- Every git object is scanned for secrets in a pre-commit hook and in CI; no market data is
  ever committed ([security policy](../SECURITY.md)).
- About $0 a month: one e2-micro, BigQuery and Cloud Storage free tiers, a manual Power BI
  refresh ([ADR-0010](adr/0010-power-bi-desktop-with-manual-refresh.md)).

## 6. What is next, and what broke (30 s)

- The daily load is paused: the vendor library behind the upstream extract stopped
  authenticating on 2026-11-10. Raw data is append-only and keyed by source, so a new
  source is one more raw table and staging model, and the reconciliation shows whether it
  agrees with the history.
- Then the hot path goes live (S1.5-S3) and the same dbt project is compared on other
  warehouses (`v1.1`+). Progress: [spec §0](spec.md#0-progress).
