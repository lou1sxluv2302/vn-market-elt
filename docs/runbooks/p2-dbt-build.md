# Runbook - P2 dbt build and reconciliation

dbt runs on your machine as `sa-dbt` (impersonation from your Google login; no key).
`dbt/profiles.yml` is git-ignored: copy `dbt/profiles.example.yml` and fill in the
project id. Run from the repository root.

```bash
dbt build --project-dir dbt --profiles-dir dbt --target dev
dbt build --project-dir dbt --profiles-dir dbt --target prod
python tools/reconcile_v1_marts.py
```

- `dev` writes `dev_staging`, `dev_intermediate`, `dev_marts_daily` (tables expire after 7
  days); `prod` writes `staging`, `intermediate`, `marts_daily`.
- The reconciler reads the prod marts as `sa-bi-reader` and v1's DuckDB read-only. Run it
  outside 15:00-16:00, when v1's daily job writes.
- A 403 right after a Terraform apply that granted Token Creator is IAM propagation: wait
  5-10 minutes.

## Holidays

The calendar after the last observed session comes from `dbt/seeds/holidays.csv`. Add next
year's dates by 1 December (a test fails otherwise) and replace `provisional` rows with the
exchanges' calendar when it is published; extend `calendar_last_date` in `dbt_project.yml`
with them.

## Data tests (P3)

`dbt build` runs the data tests after each model; a red test stops everything below it.
After a change to the tests alone, `dbt test --project-dir dbt --profiles-dir dbt --target
prod` reads the prod marts and writes nothing.

- `monitor_fallback_rows_in_universe_symbols` only warns. Above its ceiling
  (`dq_fallback_rows_ceiling` in `dbt_project.yml`, measured on prod) a source has
  stopped for a symbol that trades: find the symbols with the query in the test, then
  either fix the source or re-measure and update the ceiling with its date - never raise
  it without the measurement.
- A new data test needs a planted fault in `tools/planted_faults.py` that turns it red;
  CI fails a data test no fault reaches. Run one fault locally with
  `python tools/planted_faults.py --fault <name>`.
