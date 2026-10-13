# Runbook - P1 history load

Loads v1's raw parquet history into BigQuery `raw_vnstock` and proves it against
v1. Spec P1; code `src/vnmarket/el/load_v1_history.py`, `tools/reconcile_v1.py`.

**Run it outside 15:00-16:00 (Vietnam time)**, when v1's daily job writes its
parquet and DuckDB: both tools fail on purpose if v1's files change mid-run.

## Once: who you are

The loader runs on your machine (the history lives there) as `sa-loader`, which
can write `raw_vnstock` and nothing else. Your own Google login mints its tokens;
no key file exists and your application-default credentials are not changed.

1. `gcloud auth application-default login` has been done (step 0.3).
2. Terraform has given you Token Creator on `sa-loader` (`infra/terraform/main`).
3. `config/env/prod.yml` has `el.loader_service_account` and the `v1` paths
   (shape in `config/env/prod.example.yml`).

## Load

```bash
python -m vnmarket.el.load_v1_history
python -m vnmarket.el.load_v1_history --apply
```

The first command is a dry run: it checks every file against v1's schema and
prints counts. The second loads. It ends with two lines that must both be ✅: the
rows of every newly loaded file counted in BigQuery, and v1's files unchanged.

## Prove it

```bash
python tools/reconcile_v1.py
```

Four ✅ lines: raw = parquet per file · latest-wins reproduces v1 with residuals
within the counts measured in `config/el.yml` · reference lists = parquet · v1
unchanged. A residual above its measured count means v1 changed: explain it
before raising the number.

## If a load fails

dlt keeps the list of loaded files in its state, which is written with the data.
If a run fails part-way, run `--apply` again: a pending load package is finished
first, then new files load. If `reconcile_v1.py` then reports a file missing or
doubled, reset and reload from scratch:

```bash
dlt pipeline v1_history drop --drop-all
```

then drop the `raw_vnstock` tables in the BigQuery console and run `--apply`
again. Raw is a log, so a clean reload is the only safe repair.
