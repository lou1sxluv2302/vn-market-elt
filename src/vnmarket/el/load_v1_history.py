"""Load v1's raw parquet history into BigQuery `raw_vnstock`, append-only, with dlt.

Raw is a log (ELT): every row of every pull lands as it is - with v1's own
lineage columns (`_source_id`, `_batch_id`, `_ingested_at`, `_payload_hash`)
plus `_source_file` and `_ingest_partition` - so price revisions between pulls
(dividend and split re-adjustments) stay visible. Deduplication happens later,
in dbt staging. v1 is only read; the run fails if v1's files change meanwhile.

What is loaded (config/el.yml, `v1_history`):
- daily OHLCV from the primary and the fallback source, one file at a time;
  every file is checked against v1's schema before anything is loaded;
- the flat reference lists (symbols, exchanges, industries), as snapshots: a file
  is loaded again only when its content changed (`_source_sha256`);
- the daily foreign and proprietary flow files, which v1 rewrites whole every day: the
  same snapshot rule, partitioned and clustered like OHLCV;
- the index history, which v1 keeps only in its DuckDB table: read read-only, loaded as
  a snapshot whose hash covers the table sorted by its key.

Files already loaded are remembered in dlt state (stored in the destination with
the data, in the same load package), so a rerun loads only new files. Column
types are frozen. After the load, the rows of every OHLCV file and every current
snapshot are counted in the destination and compared with the source - all of them,
not only this run's: dlt's state can claim a load the destination never received.
Files whose name does not end in ".parquet" (v1's *.parquet.bak_<date> snapshots) are
never read; empty files are skipped and counted.

Credentials: no key. The owner's application-default credentials impersonate
`sa-loader`, which can write `raw_vnstock` and nothing else (runbook:
docs/runbooks/p1-history-load.md).

Exit codes: 0 = loaded and counted (or dry run printed) · 1 = load failed or a
count differs · 2 = usage, config or input error.

Usage:
    python -m vnmarket.el.load_v1_history                      # dry run: counts only
    python -m vnmarket.el.load_v1_history --apply [--until-ingest-date 2026-10-12]
    python -m vnmarket.el.load_v1_history --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from vnmarket.common.config import REPO_ROOT, load_config, load_env, utf8_stdio

PARTITION_KEY = "ingest_date="
OHLCV_SCHEMA = {  # v1's parquet contract; anything else is refused before loading
    "symbol": pa.string(),
    "session_date": pa.date32(),
    "open_vnd": pa.int64(),
    "high_vnd": pa.int64(),
    "low_vnd": pa.int64(),
    "close_vnd": pa.int64(),
    "volume": pa.int64(),
    "_source_id": pa.string(),
    "_ingested_at": pa.timestamp("us", tz="UTC"),
}


class InputError(Exception):
    """The input is not what v1's contract says; nothing is loaded (exit 2)."""


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
            try:
                ingest_date = dt.date.fromisoformat(part_dir.name.removeprefix(PARTITION_KEY))
            except ValueError as exc:
                raise InputError(f"unexpected partition folder {part_dir}") from exc
            if until and ingest_date > until:
                continue
            for path in sorted(part_dir.iterdir()):
                if path.is_file() and path.name.endswith(cfg["file_suffix"]):
                    relative = path.relative_to(bronze_dir).as_posix()
                    found.append(OhlcvFile(source, ingest_date, path, relative))
    return found


def check_schema(item: OhlcvFile) -> int:
    """Return the file's row count; raise InputError if it breaks v1's contract."""
    meta = pq.ParquetFile(item.path)
    schema = meta.schema_arrow
    problems = [
        f"{name}: {schema.field(name).type if name in schema.names else 'missing'} != {want}"
        for name, want in OHLCV_SCHEMA.items()
        if name not in schema.names or not schema.field(name).type.equals(want)
    ]
    if problems:
        raise InputError(f"{item.relative}: {'; '.join(problems)}")
    return meta.metadata.num_rows


OHLCV_LINEAGE = ["_source_file", "_ingest_partition"]
REFERENCE_LINEAGE = ["_source_sha256", "_loaded_at"]


def reserved_names(
    bronze_dir: Path, cfg: dict, files: list[OhlcvFile], index_table: pa.Table | None = None
) -> list[str]:
    """Columns whose name BigQuery refuses (reserved prefixes, case-insensitive). A local
    DuckDB destination accepts them, so only this check stops them before the cloud load."""
    prefixes = load_config("el")["bigquery_reserved_prefixes"]
    tables: dict[str, list[str]] = {}
    for item in files:
        tables.setdefault(cfg["ohlcv"]["table"], []).extend(pq.read_schema(item.path).names)
    tables.setdefault(cfg["ohlcv"]["table"], []).extend(OHLCV_LINEAGE)
    for name, path in reference_files(bronze_dir, cfg).items():
        tables[name] = pq.read_schema(path).names + REFERENCE_LINEAGE
    for name, path in flow_files(bronze_dir, cfg).items():
        tables[name] = pq.read_schema(path).names + REFERENCE_LINEAGE
    if index_table is not None:
        tables[cfg["index"]["table"]] = index_table.schema.names + REFERENCE_LINEAGE
    return sorted(
        f"{table}.{column}"
        for table, columns in tables.items()
        for column in set(columns)
        if column.lower().startswith(tuple(prefixes))
    )


def reference_files(bronze_dir: Path, cfg: dict) -> dict[str, Path]:
    ref = cfg["reference"]
    paths = {
        name: bronze_dir / f"source={ref['source_dir']}" / f"{name}{cfg['file_suffix']}"
        for name in ref["files"]
    }
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise InputError(f"reference files missing: {missing}")
    return paths


def flow_files(bronze_dir: Path, cfg: dict) -> dict[str, Path]:
    """{destination table: v1 file} for the daily flow snapshots."""
    flows = cfg["flows"]
    paths = {
        table: bronze_dir / f"source={flows['source_dir']}" / f"{name}{cfg['file_suffix']}"
        for name, table in flows["files"].items()
    }
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise InputError(f"flow files missing: {missing}")
    return paths


def read_index(duckdb_path: Path, cfg: dict) -> pa.Table:
    """v1's index history, sorted by its key, from v1's DuckDB opened read-only."""
    import duckdb

    ix = cfg["index"]
    with duckdb.connect(str(duckdb_path), read_only=True) as con:
        # Table and key names come from config/el.yml, not from input.
        sql = f"select * from {ix['duckdb_table']} order by {', '.join(ix['key'])}"  # noqa: S608
        return con.execute(sql).to_arrow_table()


def table_sha256(table: pa.Table) -> str:
    """Content hash of an Arrow table (its IPC stream): same rows in the same order and the
    same schema give the same hash."""
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return hashlib.sha256(sink.getvalue().to_pybytes()).hexdigest()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_fingerprint(paths: list[Path]) -> dict[str, tuple[int, int]]:
    """(size, mtime) of every file under the given roots: proof that a run left them alone."""
    found = {}
    for root in paths:
        items = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for item in items:
            stat = item.stat()
            found[str(item)] = (stat.st_size, stat.st_mtime_ns)
    return found


def loadable(table: pa.Table) -> pa.Table:
    """Make a reference table loadable from parquet into BigQuery without losing columns:
    nested values (struct, list, map) become JSON text - BigQuery cannot load its JSON type
    from parquet - and all-null columns become text, so they are not dropped."""
    import json

    for index, field in enumerate(table.schema):
        if pa.types.is_nested(field.type):
            values = [
                None if v is None else json.dumps(v, default=str, ensure_ascii=False)
                for v in table.column(index).to_pylist()
            ]
            table = table.set_column(index, field.name, pa.array(values, pa.string()))
        elif pa.types.is_null(field.type):
            table = table.set_column(index, field.name, table.column(index).cast(pa.string()))
    return table


def with_columns(table: pa.Table, **columns: tuple[Any, pa.DataType]) -> pa.Table:
    for name, (value, kind) in columns.items():
        table = table.append_column(name, pa.array([value] * table.num_rows, kind))
    return table


@dataclass(frozen=True)
class Snapshot:
    """One snapshot table: its current content hash and row count, and how to read it."""

    table: str
    digest: str
    rows: int
    read: Callable[[], pa.Table]  # called only when the snapshot is new


def snapshots(bronze_dir: Path, cfg: dict, index_table: pa.Table | None) -> list[Snapshot]:
    """Every snapshot table with the content it should hold now."""
    found = [
        Snapshot(
            f"{cfg['reference']['table_prefix']}{name}",
            sha256_of(path),
            pq.ParquetFile(path).metadata.num_rows,
            lambda path=path: loadable(pq.read_table(path)),
        )
        for name, path in reference_files(bronze_dir, cfg).items()
    ]
    found += [
        Snapshot(
            table,
            sha256_of(path),
            pq.ParquetFile(path).metadata.num_rows,
            lambda path=path: loadable(pq.read_table(path)),
        )
        for table, path in flow_files(bronze_dir, cfg).items()
    ]
    if index_table is not None:
        found.append(
            Snapshot(
                cfg["index"]["table"],
                table_sha256(index_table),
                index_table.num_rows,
                lambda: index_table,
            )
        )
    return found


def build_source(
    bronze_dir: Path,
    cfg: dict,
    files: list[OhlcvFile],
    bigquery: bool,
    skipped_empty: list[str],
    current: list[Snapshot],
) -> Any:
    """The dlt source: one OHLCV resource and one resource per snapshot table."""
    import dlt

    loaded_at = dt.datetime.now(dt.UTC)
    frozen = {"tables": "evolve", "columns": "freeze", "data_type": "freeze"}

    @dlt.resource(name=cfg["ohlcv"]["table"], write_disposition="append", schema_contract=frozen)
    def ohlcv() -> Iterator[pa.Table]:
        state = dlt.current.resource_state().setdefault("loaded_files", [])
        done = set(state)
        for item in files:
            if item.relative in done:
                continue
            table = pq.read_table(item.path)
            state.append(item.relative)
            if table.num_rows == 0:
                skipped_empty.append(item.relative)
                continue
            yield with_columns(
                table,
                **dict(
                    zip(
                        OHLCV_LINEAGE,
                        [(item.relative, pa.string()), (item.ingest_date, pa.date32())],
                        strict=True,
                    )
                ),
            )

    def resource_for(snap: Snapshot) -> Any:
        @dlt.resource(name=snap.table, write_disposition="append")
        def snapshot() -> Iterator[pa.Table]:
            state = dlt.current.resource_state()
            if state.get("sha256") == snap.digest:
                return
            yield with_columns(
                snap.read(),
                **dict(
                    zip(
                        REFERENCE_LINEAGE,
                        [(snap.digest, pa.string()), (loaded_at, pa.timestamp("us", tz="UTC"))],
                        strict=True,
                    )
                ),
            )
            state["sha256"] = snap.digest

        return snapshot

    by_table = {snap.table: resource_for(snap) for snap in current}
    resources = [ohlcv, *by_table.values()]
    if bigquery:
        from dlt.destinations.adapters import bigquery_adapter
        from dlt.destinations.impl.bigquery.bigquery_adapter import PartitionTransformation

        column = cfg["ohlcv"]["partition_by_month_of"]  # a DATE column (OHLCV_SCHEMA)
        bigquery_adapter(
            ohlcv,
            partition=PartitionTransformation("DATE_TRUNC({column_name}, MONTH)", column),
            cluster=cfg["ohlcv"]["cluster_by"],
        )
        for table in cfg["flows"]["files"].values():
            bigquery_adapter(
                by_table[table],
                partition=PartitionTransformation(
                    "DATE_TRUNC({column_name}, MONTH)", cfg["flows"]["partition_by_month_of"]
                ),
                cluster=cfg["flows"]["cluster_by"],
            )

    @dlt.source(name=cfg["pipeline_name"])
    def v1_history() -> list:
        return resources

    return v1_history()


def load(
    pipeline: Any,
    bronze_dir: Path,
    cfg: dict,
    until: dt.date | None,
    bigquery: bool,
    index_table: pa.Table | None = None,
) -> int:
    """Run the pipeline, then count every expected file and snapshot in the destination - not
    only new ones: dlt's local state can claim a load the destination never got."""
    from dlt.destinations.exceptions import DatabaseUndefinedRelation
    from dlt.pipeline.exceptions import PipelineStepFailed

    files = ohlcv_files(bronze_dir, cfg, until)
    expected = {item.relative: check_schema(item) for item in files}  # refuse before loading
    refused = reserved_names(bronze_dir, cfg, files, index_table)
    if refused:
        raise InputError(f"column names BigQuery refuses: {refused}")
    current = snapshots(bronze_dir, cfg, index_table)
    before = tree_fingerprint([bronze_dir])
    skipped_empty: list[str] = []
    try:
        pipeline.run(build_source(bronze_dir, cfg, files, bigquery, skipped_empty, current))
    except PipelineStepFailed as exc:
        print(f"🔴 load failed at step {exc.step}: {exc.exception}")
        print("   See docs/runbooks/p1-history-load.md, 'If a load fails'.")
        return 1
    wanted = [f for f, n in expected.items() if n > 0]
    counts: dict[str, int] = {}
    if wanted:
        with pipeline.sql_client() as client:
            qualified = client.make_qualified_table_name(cfg["ohlcv"]["table"])
            rows = client.execute_sql(
                f"select _source_file, count(*) from {qualified} group by _source_file"
            )
            counts = {name: n for name, n in rows}
    wrong = [f for f in wanted if counts.get(f) != expected[f]]
    for name in wrong[:20]:
        print(f"     {name}: parquet {expected[name]} rows, destination {counts.get(name)}")
    snapshot_wrong = []
    with pipeline.sql_client() as client:
        for snap in current:
            qualified = client.make_qualified_table_name(snap.table)
            try:
                # The digest is a hex string computed here, safe to inline.
                got = client.execute_sql(
                    f"select count(*) from {qualified} where _source_sha256 = '{snap.digest}'"  # noqa: S608
                )[0][0]
            except DatabaseUndefinedRelation:  # a missing table is a missing snapshot
                got = None
            if got != snap.rows:
                snapshot_wrong.append(snap.table)
                print(f"     {snap.table}: source {snap.rows} rows, destination {got}")
    changed = tree_fingerprint([bronze_dir]) != before
    print(f"Files expected: {len(wanted)}; empty files skipped: {len(skipped_empty)}")
    print(
        f"{'🔴' if wrong else '✅'} every expected file has its exact row count in the destination"
    )
    print(
        f"{'🔴' if snapshot_wrong else '✅'} every snapshot ({len(current)}) holds its "
        "current content's row count in the destination"
    )
    if wrong or snapshot_wrong:
        print("   dlt's state may list loads the destination lacks: runbook, 'If a load fails'.")
    print(f"{'🔴' if changed else '✅'} v1's files unchanged during the run")
    return 1 if wrong or snapshot_wrong or changed else 0


def dry_run(
    bronze_dir: Path, cfg: dict, until: dt.date | None, index_table: pa.Table | None = None
) -> int:
    files = ohlcv_files(bronze_dir, cfg, until)
    totals: dict[str, int] = {}
    for item in files:
        totals[item.source] = totals.get(item.source, 0) + check_schema(item)
    configured = [bronze_dir / f"source={s}" for s in cfg["ohlcv"]["sources"]]
    configured.append(bronze_dir / f"source={cfg['reference']['source_dir']}")
    never_read = [
        p
        for root in configured
        for p in root.rglob("*")
        if p.is_file() and ".parquet" in p.name and not p.name.endswith(cfg["file_suffix"])
    ]
    print(f"OHLCV files present: {len(files)} (until {until or 'latest'}); all match the schema")
    for source, rows in totals.items():
        print(f"  {source}: {rows:,} rows")
    for name, path in reference_files(bronze_dir, cfg).items():
        print(f"  reference {name}: {pq.ParquetFile(path).metadata.num_rows:,} rows")
    for table, path in flow_files(bronze_dir, cfg).items():
        print(f"  flows {table}: {pq.ParquetFile(path).metadata.num_rows:,} rows")
    if index_table is not None:
        print(f"  index {cfg['index']['table']}: {index_table.num_rows:,} rows")
    print(f"Never read (not *.parquet) in the configured sources: {len(never_read)} files")
    print("Dry run: nothing loaded. --apply loads; files already loaded are skipped then.")
    return 0


def apply(
    bronze_dir: Path, cfg: dict, env: dict, until: dt.date | None, index_table: pa.Table
) -> int:
    import os

    import dlt
    from dlt.common.configuration.specs.gcp_credentials import GcpServiceAccountCredentials
    from dlt.destinations import bigquery

    from vnmarket.common.gcp import impersonated

    for key, name in (
        ("HTTP_TIMEOUT", "bigquery_http_timeout_seconds"),
        ("FILE_UPLOAD_TIMEOUT", "bigquery_file_upload_timeout_seconds"),
        ("RETRY_DEADLINE", "bigquery_retry_deadline_seconds"),
    ):
        os.environ[f"DESTINATION__BIGQUERY__{key}"] = str(cfg[name])

    credentials = GcpServiceAccountCredentials()
    credentials.project_id = env["gcp"]["project_id"]
    # dlt's hook for non-key credentials; private in dlt 1.30.0, pinned in pyproject.
    credentials._set_default_credentials(
        impersonated(
            env["el"]["loader_service_account"],
            cfg["oauth_scope"],
            cfg["impersonation_token_seconds"],
        )
    )
    credentials.resolve()
    pipeline = dlt.pipeline(
        pipeline_name=cfg["pipeline_name"],
        destination=bigquery(credentials=credentials, location=cfg["bq_location"]),
        dataset_name=cfg["dataset"],
    )
    return load(pipeline, bronze_dir, cfg, until, bigquery=True, index_table=index_table)


def self_test() -> int:
    """Known answers on a seeded synthetic bronze tree, loaded into a local DuckDB destination."""
    import dlt
    import duckdb

    sys.path.insert(0, str(REPO_ROOT / "tests" / "fixtures"))
    import synthetic_bronze as fx

    cfg = load_config("el")["v1_history"]
    primary, fallback = cfg["ohlcv"]["sources"]
    table = f"raw.{cfg['ohlcv']['table']}"
    ref_table = f"raw.{cfg['reference']['table_prefix']}all_symbols"
    flow_table = f"raw.{cfg['flows']['files']['foreign_trade']}"
    index_dest = f"raw.{cfg['index']['table']}"
    checks: dict[str, bool] = {}

    def setup(tmp: Path) -> tuple[Path, dict, Any]:
        bronze = tmp / "bronze"
        paths = fx.bronze_tree(
            bronze, primary, fallback, cfg["reference"]["files"], list(cfg["flows"]["files"])
        )
        pipeline = dlt.pipeline(
            pipeline_name="self_test",
            pipelines_dir=str(tmp / "pipelines"),
            destination=dlt.destinations.duckdb(str(tmp / "dest.duckdb")),
            dataset_name="raw",
        )
        return bronze, paths, pipeline

    def query(tmp: Path, sql: str) -> list[tuple]:
        with duckdb.connect(str(tmp / "dest.duckdb"), read_only=True) as con:
            return con.execute(sql).fetchall()

    cutoff = dt.date(2026, 8, 31)
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        bronze, paths, pipeline = setup(tmp)
        index_v1 = fx.index_table(
            [("VNINDEX", "2026-07-31", 1300.5), ("VN30", "2026-07-31", 1400.25)]
        )
        # Planted: a backup snapshot and an empty file next to live files.
        fx.write(
            paths["first_partition"] / "a.parquet.bak_20260804",
            fx.ohlcv(primary, "2026-08-03", [("ZZZ", "2026-07-30", 1)]),
        )
        fx.write(paths["first_partition"] / "e.parquet", fx.ohlcv(primary, "2026-08-03", []))
        first_code = load(pipeline, bronze, cfg, cutoff, bigquery=False, index_table=index_v1)
        first = query(tmp, f"select count(*), count(distinct _source_file) from {table}")[0]
        revisions = query(
            tmp,
            f"select count(*) from {table} where symbol = 'AAA' and session_date = '2026-07-31'",
        )
        backups = query(tmp, f"select count(*) from {table} where symbol = 'ZZZ'")
        lineage = query(
            tmp,
            f"select count(*) from {table} where _source_file is null "
            "or _ingest_partition is null or _source_id is null",
        )
        ref_first = query(tmp, f"select count(*) from {ref_table}")
        flow_first = query(tmp, f"select count(*) from {flow_table}")
        index_first = query(tmp, f"select count(*) from {index_dest}")
        rerun_code = load(pipeline, bronze, cfg, cutoff, bigquery=False, index_table=index_v1)
        rerun = query(tmp, f"select count(*) from {table}")[0][0]
        ref_rerun = query(tmp, f"select count(*) from {ref_table}")
        flow_rerun = query(tmp, f"select count(*) from {flow_table}")
        index_rerun = query(tmp, f"select count(*) from {index_dest}")
        fx.write(
            paths["reference_dir"] / "all_symbols.parquet",
            fx.pa.table({"symbol": ["AAA", "BBB", "DDD"]}),
        )
        fx.write(paths["flows"]["foreign_trade"], fx.flows([("AAA", "2026-07-31", 5.0)] * 3))
        index_v2 = fx.index_table([("VNINDEX", "2026-07-31", 1300.5)])
        final_code = load(pipeline, bronze, cfg, None, bigquery=False, index_table=index_v2)
        final = query(tmp, f"select count(*) from {table}")[0][0]
        ref_changed = query(tmp, f"select count(*) from {ref_table}")
        flow_changed = query(tmp, f"select count(*) from {flow_table}")
        index_changed = query(tmp, f"select count(*) from {index_dest}")
        dry_code = dry_run(bronze, cfg, None)
        dry_after = query(tmp, f"select count(*) from {table}")[0][0]
        checks.update(
            {
                "control: every row of every partition loads (5 rows, 3 files)": first_code == 0
                and first == (5, 3),
                "a re-adjusted key keeps both pulls": revisions == [(2,)],
                "planted .bak snapshot is never read": backups == [(0,)],
                "every row carries its lineage": lineage == [(0,)],
                "rerun loads nothing new": rerun_code == 0 and rerun == 5,
                "cutoff held back the later partition, then it loaded": final_code == 0
                and final == 6,
                "unchanged reference file is not loaded twice": ref_first == ref_rerun == [(2,)],
                "changed reference file is loaded as a new snapshot": ref_changed == [(5,)],
                "flow and index snapshots load with their rows": flow_first == [(2,)]
                and index_first == [(2,)],
                "unchanged flow and index snapshots are not loaded twice": flow_rerun == flow_first
                and index_rerun == index_first,
                "changed flow file and index are loaded as new snapshots": flow_changed == [(5,)]
                and index_changed == [(3,)],
                "dry run writes nothing": dry_code == 0 and dry_after == final,
            }
        )

    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        bronze, paths, pipeline = setup(tmp)
        # Planted: one file whose volume drifted to float - refused before anything loads.
        drifted = fx.ohlcv(primary, "2026-09-01", [("AAA", "2026-08-29", 10_500)])
        index = drifted.schema.get_field_index("volume")
        drifted = drifted.set_column(index, "volume", drifted["volume"].cast(fx.pa.float64()))
        fx.write(paths["late"], drifted)
        try:
            load(pipeline, bronze, cfg, None, bigquery=False)
            refused = False
        except InputError:
            refused = True
        checks["planted type drift is refused before loading"] = (
            refused and not (tmp / "dest.duckdb").exists()
        )

    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        bronze, paths, pipeline = setup(tmp)
        # Planted: a reference list with a nested and an all-null column (v1's company list).
        fx.write(
            paths["reference_dir"] / "company_overview.parquet",
            fx.pa.table(
                {
                    "symbol": ["AAA", "BBB"],
                    "insight": [{"a": 1, "b": "x"}, None],
                    "tag": fx.pa.array([None, None], fx.pa.null()),
                }
            ),
        )
        nested_code = load(pipeline, bronze, cfg, None, bigquery=False)
        ref_types = dict(
            query(
                tmp,
                "select column_name, data_type from information_schema.columns "
                "where table_name = 'ref_company_overview'",
            )
        )
        checks["nested and all-null reference columns load as text, none dropped"] = (
            nested_code == 0
            and ref_types.get("insight") == "VARCHAR"
            and ref_types.get("tag") == "VARCHAR"
        )
        # Planted: dlt's state says a file is loaded, but the destination lost its rows.
        with duckdb.connect(str(tmp / "dest.duckdb")) as con:
            con.execute(f"delete from {table} where _source_file like '%/b.parquet'")
        lost_code = load(pipeline, bronze, cfg, None, bigquery=False)
        checks["planted file in state but missing from the destination fails the run"] = (
            lost_code == 1
        )
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        bronze, paths, pipeline = setup(tmp)
        clean_code = load(pipeline, bronze, cfg, None, bigquery=False)
        # Planted after a clean load: dlt's state lists a snapshot whose rows are gone.
        with duckdb.connect(str(tmp / "dest.duckdb")) as con:
            con.execute(f"delete from {flow_table}")
        lost_snapshot = load(pipeline, bronze, cfg, None, bigquery=False)
        checks["planted snapshot in state but missing from the destination fails the run"] = (
            clean_code == 0 and lost_snapshot == 1
        )

    with tempfile.TemporaryDirectory() as name:
        # read_index: sorted by key and read-only; the hash ignores insertion order.
        db = Path(name) / "v1.duckdb"
        with duckdb.connect(str(db)) as con:
            con.execute(
                "create table bronze_index (index_code varchar, session_date date, close double)"
            )
            con.execute(
                "insert into bronze_index values ('VNINDEX', '2026-07-31', 2), "
                "('VN30', '2026-07-31', 1), ('VNINDEX', '2026-07-30', 3)"
            )
        first_read = read_index(db, cfg)
        with duckdb.connect(str(db)) as con:
            rows = con.execute("select * from bronze_index").fetchall()
            con.execute("delete from bronze_index")
            for r in reversed(rows):
                con.execute("insert into bronze_index values (?, ?, ?)", list(r))
        second_read = read_index(db, cfg)
        checks["index read sorted by key; same rows in any order give the same hash"] = first_read[
            "index_code"
        ].to_pylist() == ["VN30", "VNINDEX", "VNINDEX"] and table_sha256(
            first_read
        ) == table_sha256(second_read)

    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        bronze, paths, pipeline = setup(tmp)
        # Planted: a column name BigQuery refuses (prefix _FILE_), fine in DuckDB.
        fx.write(
            paths["reference_dir"] / "industries_icb.parquet",
            fx.pa.table({"symbol": ["AAA"], "_FILE_origin": ["x"]}),
        )
        try:
            load(pipeline, bronze, cfg, None, bigquery=False)
            stopped = False
        except InputError as exc:
            stopped = "_FILE_origin" in str(exc)
        checks["planted BigQuery-reserved column name is refused before loading"] = (
            stopped and not (tmp / "dest.duckdb").exists()
        )

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


def duckdb_error() -> type[Exception]:
    import duckdb

    return duckdb.Error


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
        # Read once, read-only; v1's daily job holds the file 15:00-16:00 (runbook).
        index_table = read_index(Path(env["v1"]["duckdb_path"]), cfg)
        if args.apply:
            return apply(bronze_dir, cfg, env, args.until_ingest_date, index_table)
        return dry_run(bronze_dir, cfg, args.until_ingest_date, index_table)
    except (FileNotFoundError, KeyError, InputError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2
    except duckdb_error() as exc:
        print(f"⚪ not run: v1's DuckDB could not be read (its daily job?): {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
