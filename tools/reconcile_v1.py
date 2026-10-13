"""Reconcile the P1 history load against v1: three checks, each its own verdict.

1. raw = parquet: per loaded file, BigQuery holds exactly the parquet's rows
   (count, sums of prices and volume, date range).
2. latest-wins over raw reproduces v1's price table: per source, the newest
   pull of each (symbol, session_date) equals v1's row. Differences are
   classified; only these are allowed, because v1's own process explains them:
     - held_by_fallback: v1 kept the fallback source's row for that key;
     - absent_in_v1: v1 removed the key when it re-fetched a date range;
     - fallback_without_raw: a v1 fallback row older than v1's parquet log.
   Any value mismatch, or a v1 key missing from raw, fails.
3. reference lists = parquet: the newest snapshot of each list has the file's
   row count and content hash.

Read-only everywhere: v1's parquet and DuckDB (`read_only=True`) on this
machine, BigQuery through application-default credentials. Aggregates are
compared per symbol first; rows are fetched only for symbols that differ.

Exit codes: 0 = all checks pass · 1 = a check fails · 2 = usage, config or
access error.

Usage:
    python tools/reconcile_v1.py [--until-ingest-date YYYY-MM-DD]
    python tools/reconcile_v1.py --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from vnmarket.common.config import load_config, load_env, utf8_stdio
from vnmarket.el.load_v1_history import ohlcv_files, reference_files, sha256_of

QUERY_TIMEOUT_SECONDS = 900
PRICE_COLUMNS = ["open_vnd", "high_vnd", "low_vnd", "close_vnd", "volume"]
ALLOWED = {"held_by_fallback", "absent_in_v1", "fallback_without_raw", "equal"}

# Aggregate signature of a set of rows; equal signatures mean equal rows in practice.
SIGNATURE = ", ".join(
    ["count(*) as n", "min(session_date) as first_date", "max(session_date) as last_date"]
    + [f"sum({c}) as sum_{c}" for c in PRICE_COLUMNS]
)


# --- comparison logic (pure: arrow tables in, verdicts out) -------------------


def compare_files(parquet_stats: pa.Table, raw_stats: pa.Table) -> list[str]:
    """Check 1. Both tables: _file_name + SIGNATURE columns. Returns problems."""
    con = duckdb.connect()
    con.register("p", parquet_stats)
    con.register("r", raw_stats)
    rows = con.execute("""
        select coalesce(p._file_name, r._file_name), p.n, r.n
        from p full join r using (_file_name)
        where p.n is distinct from r.n or p.sum_close_vnd is distinct from r.sum_close_vnd
           or p.sum_volume is distinct from r.sum_volume
           or p.first_date is distinct from r.first_date or p.last_date is distinct from r.last_date
    """).fetchall()
    return [f"{name}: parquet {pn} rows, raw {rn} rows or sums differ" for name, pn, rn in rows]


def classify(raw_latest: pa.Table, v1_rows: pa.Table, primary: str) -> dict[str, int]:
    """Check 2. raw_latest: newest raw row per (source, symbol, session_date);
    v1_rows: v1's table. Both carry symbol, session_date, PRICE_COLUMNS, source.
    Returns the count per category."""
    con = duckdb.connect()
    con.register("raw", raw_latest)
    con.register("v1", v1_rows)
    same = " and ".join(f"r.{c} is not distinct from v.{c}" for c in PRICE_COLUMNS)
    counts = dict(
        con.execute(f"""
        with keys as (
            select symbol, session_date from raw
            union select symbol, session_date from v1
        )
        select category, count(*) from (
            select case
                when v.source is null then 'absent_in_v1'
                when v.source <> '{primary}' then 'held_by_fallback'
                when r.symbol is null then 'v1_key_missing_from_raw'
                when {same} then 'equal'
                else 'value_mismatch'
            end as category
            from keys k
            left join raw r on r.source = '{primary}' and r.symbol = k.symbol
                           and r.session_date = k.session_date
            left join v1 v on v.symbol = k.symbol and v.session_date = k.session_date
            where r.symbol is not null or v.source = '{primary}'
            union all
            select case
                when f.symbol is null then 'fallback_without_raw'
                when {same.replace("r.", "f.")} then 'equal'
                else 'value_mismatch'
            end
            from v1 v
            left join raw f on f.source = v.source and f.symbol = v.symbol
                           and f.session_date = v.session_date
            where v.source <> '{primary}'
        ) group by category
    """).fetchall()
    )
    return counts


# --- data access (read-only) --------------------------------------------------


def parquet_file_stats(files: list) -> pa.Table:
    con = duckdb.connect()
    parts = []
    for item in files:
        con.register("t", pq.read_table(item.path, columns=["session_date", *PRICE_COLUMNS]))
        row = con.execute(f"select {SIGNATURE} from t").fetch_arrow_table()
        parts.append(row.append_column("_file_name", pa.array([item.relative])))
        con.unregister("t")
    return pa.concat_tables(parts)


def bq_client(project: str):  # noqa: ANN201 - google type import is optional
    from google.cloud import bigquery

    return bigquery.Client(project=project)


def bq_arrow(client, sql: str, params: list | None = None) -> pa.Table:  # noqa: ANN001
    from google.cloud import bigquery

    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=params or []),
        timeout=QUERY_TIMEOUT_SECONDS,
    )
    return job.result(timeout=QUERY_TIMEOUT_SECONDS).to_arrow(create_bqstorage_client=False)


def latest_sql(table: str, where: str = "") -> str:
    return f"""
        select regexp_extract(_file_name, r'^source=([^/]+)/') as source, symbol, session_date,
               {", ".join(PRICE_COLUMNS)}
        from `{table}` {where}
        qualify row_number() over (
            partition by regexp_extract(_file_name, r'^source=([^/]+)/'), symbol, session_date
            order by _ingested_at desc, _ingest_partition desc, _file_name desc) = 1"""


def run(until: dt.date | None) -> int:
    from google.cloud import bigquery

    cfg = load_config("el")["v1_history"]
    env = load_env()
    bronze = Path(env["v1"]["bronze_dir"])
    duck_path = Path(env["v1"]["duckdb_path"])
    project = env["gcp"]["project_id"]
    table = f"{project}.{cfg['dataset']}.{cfg['ohlcv']['table']}"
    primary = cfg["ohlcv"]["sources"][0]
    client = bq_client(project)
    v1_mtime_before = duck_path.stat().st_mtime

    files = ohlcv_files(bronze, cfg, until)
    verdicts: dict[str, bool] = {}

    # 1. raw = parquet, per file
    raw_stats = bq_arrow(client, f"select _file_name, {SIGNATURE} from `{table}` group by 1")
    problems = compare_files(parquet_file_stats(files), raw_stats)
    for line in problems[:20]:
        print(f"     {line}")
    verdicts[f"raw = parquet for {len(files)} files"] = not problems

    # 2. latest-wins reproduces v1: compare per-symbol signatures, then rows for differing symbols
    with duckdb.connect(str(duck_path), read_only=True) as v1:
        # Signatures for the primary source only; every symbol that has a v1
        # fallback row is compared row by row anyway.
        v1_sig = v1.execute(
            f"""select _source_id as source, symbol, {SIGNATURE}
            from bronze_price where _source_id = $1 group by 1, 2""",
            [primary],
        ).fetch_arrow_table()
        raw_sig = bq_arrow(
            client,
            f"""select source, symbol, {SIGNATURE}
            from ({latest_sql(table)}) where source = '{primary}' group by 1, 2""",
        )
        fallback_symbols = [
            s
            for (s,) in v1.execute(
                "select distinct symbol from bronze_price where _source_id <> $1", [primary]
            ).fetchall()
        ]
        con = duckdb.connect()
        con.register("a", v1_sig)
        con.register("b", raw_sig)
        differing = [
            s
            for (s,) in con.execute(f"""
            select distinct coalesce(a.symbol, b.symbol) from a full join b
              on a.source = b.source and a.symbol = b.symbol
            where {
                " or ".join(
                    f"a.{c} is distinct from b.{c}"
                    for c in ["n", "first_date", "last_date"] + [f"sum_{p}" for p in PRICE_COLUMNS]
                )
            }
        """).fetchall()
        ]
        differing = sorted(set(differing) | set(fallback_symbols))
        con.register("d", pa.table({"symbol": differing or [""]}))
        equal_keys = con.execute("""select coalesce(sum(a.n), 0) from a join b
            on a.source = b.source and a.symbol = b.symbol
            where a.symbol not in (select symbol from d)""").fetchone()[0]
        counts: dict[str, int] = {}
        if differing:
            v1_rows = v1.execute(
                f"select _source_id as source, symbol, session_date, {', '.join(PRICE_COLUMNS)} "
                "from bronze_price where symbol in (select unnest($1))",
                [differing],
            ).fetch_arrow_table()
            raw_rows = bq_arrow(
                client,
                latest_sql(table, "where symbol in unnest(@symbols)"),
                [bigquery.ArrayQueryParameter("symbols", "STRING", differing)],
            )
            counts = classify(raw_rows, v1_rows, primary)
    print(f"     symbols compared row by row: {len(differing)}; categories: {counts or 'none'}")
    print(f"     primary keys in symbols whose signature matched exactly: {equal_keys:,}")
    verdicts["latest-wins over raw reproduces v1 (only explained differences)"] = (
        set(counts) <= ALLOWED
    )

    # 3. reference lists = parquet (newest snapshot)
    ref_ok = True
    for name, path in reference_files(bronze, cfg).items():
        ref_table = f"{project}.{cfg['dataset']}.{cfg['reference']['table_prefix']}{name}"
        got = bq_arrow(
            client,
            f"""select _file_sha256, count(*) as n from `{ref_table}`
            group by 1 order by max(_loaded_at) desc limit 1""",
        ).to_pylist()
        want = (sha256_of(path), pq.ParquetFile(path).metadata.num_rows)
        if not got or (got[0]["_file_sha256"], got[0]["n"]) != want:
            ref_ok = False
            print(
                f"     {name}: raw {got[:1]} vs file rows {want[1]} (or content changed since load)"
            )
    verdicts["reference lists = parquet (newest snapshot)"] = ref_ok

    verdicts["v1's DuckDB file unchanged during the run"] = (
        duck_path.stat().st_mtime == v1_mtime_before
    )
    for name, ok in verdicts.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(verdicts.values()) else 1


def self_test() -> int:
    """Known answers on synthetic tables; each planted fault fails exactly its own check."""
    primary, fallback = "vnstock_quote", "vndirect_dchart"

    def rows(*items: tuple) -> pa.Table:
        source, symbol, date, close = zip(*items, strict=True)
        n = len(items)
        return pa.table(
            {
                "source": list(source),
                "symbol": list(symbol),
                "session_date": [dt.date.fromisoformat(d) for d in date],
                **{c: pa.array([0] * n, pa.int64()) for c in PRICE_COLUMNS if c != "close_vnd"},
                "close_vnd": pa.array(close, pa.int64()),
            }
        )

    raw = rows(
        (primary, "AAA", "2026-07-30", 100),
        (primary, "AAA", "2026-07-31", 99),
        (primary, "BBB", "2026-07-31", 50),
        (primary, "CCC", "2026-07-31", 70),
        (fallback, "BBB", "2026-07-31", 51),
    )
    v1 = rows(
        (primary, "AAA", "2026-07-30", 100),
        (primary, "AAA", "2026-07-31", 99),
        (fallback, "BBB", "2026-07-31", 51),  # held by fallback
        (fallback, "DDD", "2013-01-02", 10),
    )  # fallback without raw
    control = classify(raw, v1, primary)

    mismatch = classify(
        raw, rows((primary, "AAA", "2026-07-30", 100), (primary, "AAA", "2026-07-31", 98)), primary
    )
    missing = classify(
        raw, rows((primary, "AAA", "2026-07-30", 100), (primary, "EEE", "2026-07-31", 5)), primary
    )

    stats = pa.table(
        {
            "_file_name": ["a", "b"],
            "n": [2, 3],
            "first_date": [dt.date(2026, 1, 1)] * 2,
            "last_date": [dt.date(2026, 1, 2)] * 2,
            **{f"sum_{c}": [10, 20] for c in PRICE_COLUMNS},
        }
    )
    short = stats.set_column(1, "n", pc.cast(pa.array([2, 2]), pa.int64()))

    checks = {
        "control: explained differences only": control
        == {"equal": 3, "held_by_fallback": 1, "absent_in_v1": 1, "fallback_without_raw": 1},
        "control passes the allowed-set rule": set(control) <= ALLOWED,
        "planted price change is a value_mismatch": "value_mismatch" in mismatch,
        "planted v1 key missing from raw is caught": "v1_key_missing_from_raw" in missing,
        "file stats: identical tables give no problem": compare_files(stats, stats) == [],
        "file stats: a short file is reported": len(compare_files(stats, short)) == 1,
        "file stats: a file missing from raw is reported": len(
            compare_files(stats, stats.slice(0, 1))
        )
        == 1,
    }
    checks["an unknown argument is rejected with exit 2"] = (
        subprocess.run(  # noqa: S603
            [sys.executable, __file__, "--bogus"], capture_output=True, timeout=120
        ).returncode
        == 2
    )
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--until-ingest-date",
        type=dt.date.fromisoformat,
        help="the cutoff used for the load (YYYY-MM-DD)",
    )
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    if args.self_test:
        return self_test()
    try:
        return run(args.until_ingest_date)
    except (FileNotFoundError, KeyError, ImportError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
