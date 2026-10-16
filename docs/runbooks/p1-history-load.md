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
python -m vnmarket.el.load_v1_history --apply --until-ingest-date 2026-08-03
python -m vnmarket.el.load_v1_history --apply
```

The first command is a dry run: it checks every file against v1's schema and
BigQuery's column-name rules and prints counts. The second loads only the first
pull - a small smoke load that meets BigQuery's own rules early. The third loads
the rest (files already loaded are skipped). It ends with three lines that must all be ✅:
the rows of every expected file counted in BigQuery, every snapshot table holding its
current content's rows, and v1's files unchanged.

The same run loads the snapshots: the reference lists, the daily foreign and proprietary
flow files, and the index history read read-only from v1's DuckDB (v1 keeps no index
log). A snapshot is loaded again only when its content changed. v1 rewrites the flow
files every day, so each later run adds a full copy of them (about 1 GB for the foreign
flow file): reload when you need newer history, not every day. If v1's daily job holds
its DuckDB, the loader stops with "⚪ not run" before loading anything.

## Prove it

```bash
python tools/reconcile_v1.py
```

Five ✅ lines: raw = parquet per file · latest-wins reproduces v1 with residuals
within the counts measured in `config/el.yml` · reference lists = parquet · flows
and index = v1 (newest snapshot: content hash and per-symbol signatures) · v1
unchanged. A residual above its measured count means v1 changed: explain it
before raising the number.

## If a load fails

dlt records the files it extracted in a local working folder
(`~/.dlt/pipelines/v1_history`) before they reach BigQuery. If a run fails at
the load step, that record can claim files the destination never received. The
loader therefore counts **every** expected file in BigQuery after each run, and
fails if any is missing or short.

1. Look at the destination: list the tables in `raw_vnstock` (console, or
   `bq ls raw_vnstock`).
2. **Destination empty** (the failure came before any table was written):
   delete the local working folder `~/.dlt/pipelines/v1_history`, fix the cause,
   run `--apply` again. Nothing else holds state.
3. **Destination holds data:** reset both sides, then reload from scratch -
   `dlt pipeline v1_history drop --drop-all`, delete the `raw_vnstock` tables in
   the console, run `--apply`. Raw is a log, so a clean reload is the only safe
   repair.

Seen on the first run (2026-10-13): BigQuery refused a nested column of
`company_overview` (its JSON type cannot be loaded from parquet). Nothing had
been written; the local folder claimed all 145 files. Fixed in the loader
(nested and all-null reference columns load as text) and case 2 applied.
The second run that day hit BigQuery's reserved column prefixes (`_FILE_`): the
lineage columns were renamed `_source_file` and `_source_sha256`, and the loader
now checks every column name against `bigquery_reserved_prefixes` before loading.
