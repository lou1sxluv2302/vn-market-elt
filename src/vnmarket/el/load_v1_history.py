"""Load v1's raw parquet history into BigQuery `raw_vnstock`, append-only, with dlt.

Raw is a log (ELT): every row of every ingest partition lands as it is, so the
price revisions between pulls (dividend and split re-adjustments) stay visible;
deduplication happens later, in dbt staging. v1 is only read.

What is loaded (config/el.yml, `v1_history`):
- daily OHLCV from the primary and the fallback source, one file at a time, with
  `_file_name` and `_ingest_partition` lineage columns;
- the flat reference lists (symbols, exchanges, industries), as snapshots: a file
  is loaded again only when its content changed (`_file_sha256`).

Files already loaded are remembered in dlt state (kept in the destination), so a
rerun loads only new files. `--until-ingest-date` makes a load reproducible while
v1 keeps writing. Files not ending in ".parquet" (v1's *.parquet.bak_<date>
snapshots) are never read.

Credentials: no key. The owner's application-default credentials mint a
short-lived token for `sa-loader` (impersonation; the owner holds Token Creator
on it), which can write `raw_vnstock` and nothing else. The owner's own ADC file
is left as it is, so Terraform keeps working.

Exit codes: 0 = done (or dry run printed) · 1 = load failed · 2 = usage or config error.

Usage:
    python -m vnmarket.el.load_v1_history                      # dry run: counts only
    python -m vnmarket.el.load_v1_history --apply [--until-ingest-date 2026-10-12]
    python -m vnmarket.el.load_v1_history --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from vnmarket.common.config import load_config, load_env, utf8_stdio

PARTITION_KEY = "ingest_date="


@dataclass(frozen=True)
class OhlcvFile:
    source: str
    ingest_date: dt.date
    path: Path
    relative: str  # path under the bronze root, POSIX style: the identity of a file


def ohlcv_files(bronze_dir: Path, cfg: dict, until: dt.date | None) -> list[OhlcvFile]:
    """Every OHLCV parquet file of the configured sources, oldest partition first."""
    found = []
    for source in cfg["ohlcv"]["sources"]:
        base = bronze_dir / f"source={source}" / f"dataset={cfg['ohlcv']['dataset_dir']}"
        for part_dir in sorted(base.glob(f"{PARTITION_KEY}*")):
            ingest_date = dt.date.fromisoformat(part_dir.name.removeprefix(PARTITION_KEY))
            if until and ingest_date > until:
                continue
            for path in sorted(part_dir.iterdir()):
                if path.is_file() and path.name.endswith(cfg["file_suffix"]):
                    found.append(
                        OhlcvFile(
                            source, ingest_date, path, path.relative_to(bronze_dir).as_posix()
                        )
                    )
    return found


def reference_files(bronze_dir: Path, cfg: dict) -> dict[str, Path]:
    ref = cfg["reference"]
    paths = {
        name: bronze_dir / f"source={ref['source_dir']}" / f"{name}{cfg['file_suffix']}"
        for name in ref["files"]
    }
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"reference files missing: {missing}")
    return paths


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def with_columns(table: pa.Table, **columns: Any) -> pa.Table:
    for name, value in columns.items():
        table = table.append_column(name, pa.array([value] * table.num_rows))
    return table


def build_source(bronze_dir: Path, cfg: dict, until: dt.date | None, bigquery: bool) -> Any:
    """The dlt source: one OHLCV resource and one resource per reference list."""
    import dlt

    files = ohlcv_files(bronze_dir, cfg, until)
    refs = reference_files(bronze_dir, cfg)
    loaded_at = dt.datetime.now(dt.UTC)

    @dlt.resource(name=cfg["ohlcv"]["table"], write_disposition="append")
    def ohlcv() -> Iterator[pa.Table]:
        state = dlt.current.resource_state().setdefault("loaded_files", [])
        done = set(state)
        for item in files:
            if item.relative in done:
                continue
            table = pq.read_table(item.path)
            yield with_columns(table, _file_name=item.relative, _ingest_partition=item.ingest_date)
            state.append(item.relative)

    def reference(name: str, path: Path) -> Any:
        @dlt.resource(name=f"{cfg['reference']['table_prefix']}{name}", write_disposition="append")
        def snapshot() -> Iterator[pa.Table]:
            state = dlt.current.resource_state()
            digest = sha256_of(path)
            if state.get("sha256") == digest:
                return
            yield with_columns(pq.read_table(path), _file_sha256=digest, _loaded_at=loaded_at)
            state["sha256"] = digest

        return snapshot

    resources = [ohlcv] + [reference(name, path) for name, path in refs.items()]
    if bigquery:
        from dlt.destinations.adapters import bigquery_adapter
        from dlt.destinations.impl.bigquery.bigquery_adapter import PartitionTransformation

        column = cfg["ohlcv"]["partition_by_month_of"]
        bigquery_adapter(
            ohlcv,
            partition=PartitionTransformation("DATE_TRUNC({column_name}, MONTH)", column),
            cluster=cfg["ohlcv"]["cluster_by"],
        )

    @dlt.source(name=cfg["pipeline_name"])
    def v1_history() -> list:
        return resources

    return v1_history()


def dry_run(bronze_dir: Path, cfg: dict, until: dt.date | None) -> int:
    files = ohlcv_files(bronze_dir, cfg, until)
    totals: dict[str, int] = {}
    for item in files:
        totals[item.source] = (
            totals.get(item.source, 0) + pq.ParquetFile(item.path).metadata.num_rows
        )
    skipped = [
        p
        for p in bronze_dir.rglob("*")
        if p.is_file() and ".parquet" in p.name and not p.name.endswith(cfg["file_suffix"])
    ]
    print(f"OHLCV files to consider: {len(files)} (until {until or 'latest'})")
    for source, rows in totals.items():
        print(f"  {source}: {rows:,} rows")
    for name, path in reference_files(bronze_dir, cfg).items():
        print(f"  reference {name}: {pq.ParquetFile(path).metadata.num_rows:,} rows")
    print(f"Never read (not *.parquet): {len(skipped)} files")
    print("Dry run: nothing loaded. Add --apply to load (files already loaded are skipped).")
    return 0


def apply(bronze_dir: Path, cfg: dict, env: dict, until: dt.date | None) -> int:
    import dlt
    import google.auth
    from dlt.common.configuration.specs.gcp_credentials import GcpServiceAccountCredentials
    from dlt.destinations import bigquery
    from google.auth import impersonated_credentials

    os.environ["DESTINATION__BIGQUERY__HTTP_TIMEOUT"] = str(cfg["bigquery_http_timeout_seconds"])
    os.environ["DESTINATION__BIGQUERY__FILE_UPLOAD_TIMEOUT"] = str(
        cfg["bigquery_file_upload_timeout_seconds"]
    )
    os.environ["DESTINATION__BIGQUERY__RETRY_DEADLINE"] = str(
        cfg["bigquery_retry_deadline_seconds"]
    )

    # No key anywhere: the owner's application-default credentials mint a
    # short-lived token for sa-loader, which may write raw_vnstock and nothing else.
    owner, _ = google.auth.default(scopes=[cfg["oauth_scope"]])
    loader = impersonated_credentials.Credentials(
        source_credentials=owner,
        target_principal=env["el"]["loader_service_account"],
        target_scopes=[cfg["oauth_scope"]],
        lifetime=cfg["impersonation_lifetime_seconds"],
    )
    credentials = GcpServiceAccountCredentials()
    credentials.project_id = env["gcp"]["project_id"]
    credentials._set_default_credentials(loader)  # dlt's hook for non-key credentials
    credentials.resolve()

    pipeline = dlt.pipeline(
        pipeline_name=cfg["pipeline_name"],
        destination=bigquery(credentials=credentials, location=cfg["bq_location"]),
        dataset_name=cfg["dataset"],
    )
    info = pipeline.run(build_source(bronze_dir, cfg, until, bigquery=True))
    print(info)
    return 1 if info.has_failed_jobs else 0


def self_test() -> int:
    """Known answers on a synthetic bronze tree, loaded into a local DuckDB destination."""
    import dlt
    import duckdb

    cfg = load_config("el")["v1_history"]

    def ohlcv_table(rows: list[tuple]) -> pa.Table:
        symbols, dates, closes = zip(*rows, strict=True)
        return pa.table(
            {
                "symbol": list(symbols),
                "session_date": [dt.date.fromisoformat(d) for d in dates],
                "close_vnd": pa.array(closes, pa.int64()),
                "_ingested_at": [dt.datetime(2026, 1, 1, tzinfo=dt.UTC)] * len(rows),
            }
        )

    def write(path: Path, table: pa.Table) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, path)

    with tempfile.TemporaryDirectory() as tmp:
        bronze = Path(tmp) / "bronze"
        primary, fallback = cfg["ohlcv"]["sources"]
        part = f"dataset={cfg['ohlcv']['dataset_dir']}"
        write(
            bronze / f"source={primary}/{part}/ingest_date=2026-08-03/a.parquet",
            ohlcv_table([("AAA", "2026-07-30", 10_000), ("AAA", "2026-07-31", 10_100)]),
        )
        # The same key again in a later pull, re-adjusted: both rows must be kept.
        write(
            bronze / f"source={primary}/{part}/ingest_date=2026-08-07/b.parquet",
            ohlcv_table([("AAA", "2026-07-31", 9_900), ("BBB", "2026-07-31", 5_000)]),
        )
        write(
            bronze / f"source={fallback}/{part}/ingest_date=2026-08-07/c.parquet",
            ohlcv_table([("CCC", "2026-07-31", 7_000)]),
        )
        late = bronze / f"source={primary}/{part}/ingest_date=2026-09-01/d.parquet"
        write(late, ohlcv_table([("AAA", "2026-08-29", 10_500)]))
        # Planted: a backup snapshot next to a live file must never be read.
        write(
            bronze / f"source={primary}/{part}/ingest_date=2026-08-03/a.parquet.bak_20260804",
            ohlcv_table([("ZZZ", "2026-07-30", 1)]),
        )
        ref_dir = bronze / f"source={cfg['reference']['source_dir']}"
        for name in cfg["reference"]["files"]:
            write(ref_dir / f"{name}.parquet", pa.table({"symbol": ["AAA", "BBB"]}))

        def run(until: dt.date | None) -> None:
            pipeline = dlt.pipeline(
                pipeline_name="self_test",
                pipelines_dir=str(Path(tmp) / "pipelines"),
                destination=dlt.destinations.duckdb(str(Path(tmp) / "dest.duckdb")),
                dataset_name="raw",
            )
            pipeline.run(build_source(bronze, cfg, until, bigquery=False))

        def query(sql: str) -> list[tuple]:
            with duckdb.connect(str(Path(tmp) / "dest.duckdb"), read_only=True) as con:
                return con.execute(sql).fetchall()

        table = f"raw.{cfg['ohlcv']['table']}"
        run(until=dt.date(2026, 8, 31))
        first = query(f"select count(*), count(distinct _file_name) from {table}")[0]
        revisions = query(
            f"select count(*) from {table} where symbol='AAA' and session_date='2026-07-31'"
        )
        backups = query(f"select count(*) from {table} where symbol='ZZZ'")
        ref_first = query(f"select count(*) from raw.{cfg['reference']['table_prefix']}all_symbols")
        run(until=dt.date(2026, 8, 31))
        rerun = query(f"select count(*) from {table}")[0][0]
        ref_rerun = query(f"select count(*) from raw.{cfg['reference']['table_prefix']}all_symbols")
        write(ref_dir / "all_symbols.parquet", pa.table({"symbol": ["AAA", "BBB", "DDD"]}))
        run(until=None)
        final = query(f"select count(*) from {table}")[0][0]
        ref_changed = query(
            f"select count(*) from raw.{cfg['reference']['table_prefix']}all_symbols"
        )
        lineage = query(
            f"select count(*) from {table} where _file_name is null or _ingest_partition is null"
        )

    checks = {
        "every row of every partition is loaded (5 rows, 3 files)": first == (5, 3),
        "a re-adjusted key keeps both pulls": revisions == [(2,)],
        "planted .bak snapshot is never read": backups == [(0,)],
        "rerun loads nothing new": rerun == 5,
        "cutoff held back the later partition, then it loaded": final == 6,
        "unchanged reference file is not loaded twice": ref_first == ref_rerun == [(2,)],
        "changed reference file is loaded as a new snapshot": ref_changed == [(5,)],
        "every row carries its lineage": lineage == [(0,)],
    }
    checks["an unknown argument is rejected with exit 2"] = (
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "vnmarket.el.load_v1_history", "--bogus"],
            capture_output=True,
            timeout=120,
        ).returncode
        == 2
    )
    print()
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--apply", action="store_true", help="load into BigQuery (default: dry run)"
    )
    parser.add_argument(
        "--until-ingest-date",
        type=dt.date.fromisoformat,
        help="load partitions up to this ingest date (YYYY-MM-DD)",
    )
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    if args.self_test:
        return self_test()
    try:
        cfg = load_config("el")["v1_history"]
        env = load_env()
        bronze_dir = Path(env["v1"]["bronze_dir"])
    except (FileNotFoundError, KeyError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2
    if args.apply:
        return apply(bronze_dir, cfg, env, args.until_ingest_date)
    return dry_run(bronze_dir, cfg, args.until_ingest_date)


if __name__ == "__main__":
    sys.exit(main())
