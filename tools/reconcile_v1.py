"""Reconcile the P1 history load against v1: each check is its own verdict.

1. raw = parquet: for every file up to the newest pull in raw, BigQuery holds
   exactly the parquet's rows (count, date range, sums and a date-weighted
   checksum of every price and volume column). A file loaded twice, cut short or
   missing fails.
2. latest-wins over raw reproduces v1's price table. Per source, the newest pull
   of each (symbol, session_date) is compared with v1's `bronze_price`. v1 did not
   take the newest pull across sources: it wrote only the source it used that day,
   so the comparison is per source, and these differences are explained by v1's
   own process - each allowed up to the count measured in config/el.yml:
     - held_by_fallback: v1 kept the fallback source's row for a primary key;
     - absent_in_v1: v1 removed the key when it re-fetched a date range;
     - fallback_batch_not_in_log: a v1 fallback row written by a batch that never
       reached v1's parquet log (no raw row carries its `_ingested_at`); measured:
       one batch, 2026-08-06 11:40 ICT, sessions 2026-08-03 to 08-05.
   A value mismatch, a v1 key missing from raw, a fallback row from a batch that
   is in the log but differs from raw or is missing from it, or a row from an
   unknown source fails.
3. reference lists = parquet: the newest snapshot of each list has the file's row
   count and content hash.
4. v1 untouched: v1's bronze tree and DuckDB files are byte-for-byte as before.

Per-symbol signatures (count, dates, sums, date-weighted checksums) are compared
first; rows are fetched only for symbols whose signature differs, plus every
symbol v1 holds from the fallback source. The weighted checksum catches values
moved between dates and changes that cancel in a plain sum; it is not a
cryptographic hash, so equal signatures are strong evidence, not proof.

Latest-wins order: newest `_ingested_at`, then newest `_ingest_partition`, then
the later file name. v1 kept the last row of a batch for duplicate keys, which
the first two keys reproduce; the third only breaks ties v1 never had.

Read-only: v1's parquet and DuckDB (`read_only=True`); BigQuery as `sa-loader`
through impersonation (scoped to `raw_vnstock`). Run it outside 15:00-16:00,
when v1's daily job writes.

Exit codes: 0 = all checks pass · 1 = a check fails · 2 = usage, config or
access error.

Usage:
    python tools/reconcile_v1.py
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
import pyarrow.parquet as pq

from vnmarket.common.config import load_config, load_env, utf8_stdio
from vnmarket.el.load_v1_history import (
    InputError,
    ohlcv_files,
    reference_files,
    sha256_of,
    tree_fingerprint,
)

PRICE_COLUMNS = ["open_vnd", "high_vnd", "low_vnd", "close_vnd", "volume"]
SIGNATURE_COLUMNS = ["n", "first_date", "last_date"] + [
    f"{kind}_{c}" for c in PRICE_COLUMNS for kind in ("sum", "wsum")
]
EXPLAINED = {"held_by_fallback", "absent_in_v1", "fallback_batch_not_in_log"}
PASSING = {"equal", "fallback_equal"} | EXPLAINED


# --- SQL shared by BigQuery and DuckDB ----------------------------------------


def signature(dialect: str, modulus: int) -> str:
    """Aggregate signature of a set of rows; `dialect` is 'bigquery' or 'duckdb'."""
    day = (
        "unix_date(session_date)"
        if dialect == "bigquery"
        else "date_diff('day', date '1970-01-01', session_date)"
    )
    weight = f"(mod({day}, {modulus}) + 1)"
    parts = ["count(*) as n", "min(session_date) as first_date", "max(session_date) as last_date"]
    for c in PRICE_COLUMNS:
        parts += [f"sum({c}) as sum_{c}", f"sum({c} * {weight}) as wsum_{c}"]
    return ", ".join(parts)


def latest_sql(table: str, where: str = "") -> str:
    """Newest pull of each (source, symbol, session_date); valid in BigQuery and DuckDB."""
    return f"""
        select _source_id as source, symbol, session_date, {", ".join(PRICE_COLUMNS)}
        from {table} {where}
        qualify row_number() over (
            partition by _source_id, symbol, session_date
            order by _ingested_at desc, _ingest_partition desc, _source_file desc) = 1"""


def differing(con: duckdb.DuckDBPyConnection, left: str, right: str, keys: list[str]) -> list:
    """Keys of the rows of two registered signature tables that are not identical."""
    on = " and ".join(f"a.{k} = b.{k}" for k in keys)
    unequal = " or ".join(f"a.{c} is distinct from b.{c}" for c in SIGNATURE_COLUMNS)
    pick = ", ".join(f"coalesce(a.{k}, b.{k})" for k in keys)
    return con.execute(
        f"select {pick} from {left} a full join {right} b on {on} where {unequal}"
    ).fetchall()


# --- comparison logic (pure: arrow tables in, verdicts out) -------------------


def compare_files(parquet_stats: pa.Table, raw_stats: pa.Table) -> list[str]:
    """Check 1. Both: _source_file + SIGNATURE_COLUMNS. One line per file that differs."""
    con = duckdb.connect()
    con.register("p", parquet_stats)
    con.register("r", raw_stats)
    return [
        f"{name}: rows or sums differ" for (name,) in differing(con, "p", "r", ["_source_file"])
    ]


def classify(
    raw_latest: pa.Table, v1_rows: pa.Table, primary: str, fallback: str, raw_batches: pa.Table
) -> dict[str, int]:
    """Check 2. raw_latest: newest raw row per (source, symbol, session_date); v1_rows: v1's
    rows with `source` and `_ingested_at`; raw_batches: distinct (source, _ingested_at) in raw.
    Each primary key and each v1 non-primary row gets exactly one category."""
    con = duckdb.connect()
    con.register("raw", raw_latest)
    con.register("v1", v1_rows)
    con.register("batches", raw_batches)
    same = " and ".join(f"r.{c} is not distinct from v.{c}" for c in PRICE_COLUMNS)
    rows = con.execute(f"""
        with primary_keys as (
            select symbol, session_date from raw where source = '{primary}'
            union select symbol, session_date from v1 where source = '{primary}'
        )
        select category, count(*) from (
            select case
                when v.source is null then 'absent_in_v1'
                when v.source <> '{primary}' then 'held_by_fallback'
                when r.symbol is null then 'v1_key_missing_from_raw'
                when {same} then 'equal'
                else 'value_mismatch'
            end as category
            from primary_keys k
            left join raw r on r.source = '{primary}' and r.symbol = k.symbol
                           and r.session_date = k.session_date
            left join v1 v on v.symbol = k.symbol and v.session_date = k.session_date
            union all
            select case
                when v.source <> '{fallback}' then 'unknown_source'
                when r.symbol is not null and {same} then 'fallback_equal'
                when b.source is null then 'fallback_batch_not_in_log'
                when r.symbol is not null then 'fallback_mismatch'
                else 'fallback_missing_from_raw'
            end
            from v1 v
            left join raw r on r.source = v.source and r.symbol = v.symbol
                           and r.session_date = v.session_date
            left join batches b on b.source = v.source and b._ingested_at = v._ingested_at
            where v.source <> '{primary}'
        ) group by category
    """).fetchall()
    return dict(rows)


def verdict(counts: dict[str, int], allowed: dict[str, int]) -> list[str]:
    """Problems: any failing category, or an explained category above its measured count."""
    problems = [f"{c}: {n}" for c, n in counts.items() if c not in PASSING]
    problems += [
        f"{c}: {counts[c]} > {allowed[c]} measured"
        for c in sorted(EXPLAINED)
        if counts.get(c, 0) > allowed[c]
    ]
    return problems


# --- data access (read-only) --------------------------------------------------


def parquet_file_stats(files: list, modulus: int) -> pa.Table:
    con = duckdb.connect()
    parts = []
    sig = signature("duckdb", modulus)
    for item in files:
        con.register("t", pq.read_table(item.path, columns=["session_date", *PRICE_COLUMNS]))
        row = con.execute(f"select {sig} from t").to_arrow_table()
        parts.append(row.append_column("_source_file", pa.array([item.relative])))
        con.unregister("t")
    return pa.concat_tables(parts)


def run() -> int:
    from google.cloud import bigquery

    from vnmarket.common.gcp import impersonated

    el = load_config("el")
    cfg, rec = el["v1_history"], el["reconcile_v1"]
    env = load_env()
    bronze = Path(env["v1"]["bronze_dir"])
    duck_path = Path(env["v1"]["duckdb_path"])
    project = env["gcp"]["project_id"]
    table = f"`{project}.{cfg['dataset']}.{cfg['ohlcv']['table']}`"
    primary, fallback = cfg["ohlcv"]["sources"]
    timeout = rec["query_timeout_seconds"]
    modulus = rec["checksum_modulus"]
    credentials = impersonated(
        env["el"]["loader_service_account"], cfg["oauth_scope"], cfg["impersonation_token_seconds"]
    )
    client = bigquery.Client(project=project, credentials=credentials)

    def bq(sql: str, params: list | None = None) -> pa.Table:
        config = bigquery.QueryJobConfig(query_parameters=params or [])
        job = client.query(sql, job_config=config, timeout=timeout)
        return job.result(timeout=timeout).to_arrow(create_bqstorage_client=False)

    v1_paths = [bronze, duck_path, duck_path.with_suffix(duck_path.suffix + ".wal")]
    before = tree_fingerprint([p for p in v1_paths if p.exists()])
    verdicts: dict[str, bool] = {}

    # 1. raw = parquet, per file, up to the newest pull in raw
    until = bq(f"select max(_ingest_partition) as last_date from {table}").to_pylist()[0][
        "last_date"
    ]
    raw_batches = bq(
        f"select distinct _source_id as source, _ingested_at from {table} "
        f"where _source_id = '{fallback}'"
    )
    files = ohlcv_files(bronze, cfg, until)
    raw_stats = bq(f"select _source_file, {signature('bigquery', modulus)} from {table} group by 1")
    problems = compare_files(parquet_file_stats(files, modulus), raw_stats)
    for line in problems[:20]:
        print(f"     {line}")
    verdicts[f"raw = parquet for {len(files)} files up to {until}"] = not problems

    # 2. latest-wins over raw reproduces v1
    with duckdb.connect(str(duck_path), read_only=True) as v1:
        v1_sig = v1.execute(
            f"select symbol, {signature('duckdb', modulus)} from bronze_price "
            "where _source_id = $1 group by 1",
            [primary],
        ).to_arrow_table()
        raw_sig = bq(
            f"select symbol, {signature('bigquery', modulus)} "
            f"from ({latest_sql(table)}) where source = '{primary}' group by 1"
        )
        fallback_symbols = {
            s
            for (s,) in v1.execute(
                "select distinct symbol from bronze_price where _source_id <> $1", [primary]
            ).fetchall()
        }
        con = duckdb.connect()
        con.register("a", v1_sig)
        con.register("b", raw_sig)
        changed = {s for (s,) in differing(con, "a", "b", ["symbol"])}
        symbols = sorted(changed | fallback_symbols)
        counts: dict[str, int] = {}
        if symbols:
            v1_rows = v1.execute(
                f"select _source_id as source, symbol, session_date, _ingested_at, "
                f"{', '.join(PRICE_COLUMNS)} from bronze_price "
                "where symbol in (select unnest($1))",
                [symbols],
            ).to_arrow_table()
            raw_rows = bq(
                latest_sql(table, "where symbol in unnest(@symbols)"),
                [bigquery.ArrayQueryParameter("symbols", "STRING", symbols)],
            )
            counts = classify(raw_rows, v1_rows, primary, fallback, raw_batches)
    print(
        f"     symbols with differing signatures: {len(changed)}; "
        f"compared row by row: {len(symbols)} of {len(raw_sig)}"
    )
    print(f"     categories: {counts or 'none'}")
    problems = verdict(counts, rec["allowed_residuals"])
    for line in problems:
        print(f"     {line}")
    verdicts["latest-wins over raw reproduces v1, residuals within measured counts"] = not problems

    # 3. reference lists = parquet (newest snapshot)
    ref_ok = True
    for name, path in reference_files(bronze, cfg).items():
        ref = f"`{project}.{cfg['dataset']}.{cfg['reference']['table_prefix']}{name}`"
        got = bq(
            f"select _source_sha256, count(*) as n from {ref} "
            "group by 1 order by max(_loaded_at) desc limit 1"
        ).to_pylist()
        want = (sha256_of(path), pq.ParquetFile(path).metadata.num_rows)
        if not got or (got[0]["_source_sha256"], got[0]["n"]) != want:
            ref_ok = False
            print(f"     {name}: newest snapshot {got[:1]} vs file rows {want[1]}")
    verdicts["reference lists = parquet (newest snapshot)"] = ref_ok

    # 4. v1 untouched
    after = tree_fingerprint([p for p in v1_paths if p.exists()])
    verdicts["v1's files unchanged during the run (rerun outside 15:00-16:00 if not)"] = (
        after == before
    )

    for name, ok in verdicts.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(verdicts.values()) else 1


def self_test() -> int:
    """Known answers on synthetic tables; each planted fault fails exactly its own check."""
    primary, fallback = "vnstock_quote", "vndirect_dchart"
    modulus = 1009
    early = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    late = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
    raw_batches = pa.table({"source": [fallback], "_ingested_at": [late]})

    def rows(*items: tuple) -> pa.Table:
        """items: (source, symbol, date, close[, ingested_at])"""
        items = [i if len(i) == 5 else (*i, late) for i in items]
        source, symbol, date, close, ingested = zip(*items, strict=True)
        n = len(items)
        return pa.table(
            {
                "source": list(source),
                "symbol": list(symbol),
                "session_date": [dt.date.fromisoformat(d) for d in date],
                "_ingested_at": list(ingested),
                **{c: pa.array([1] * n, pa.int64()) for c in PRICE_COLUMNS if c != "close_vnd"},
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
    base = rows(
        (primary, "AAA", "2026-07-30", 100),
        (primary, "AAA", "2026-07-31", 99),
        (fallback, "BBB", "2026-07-31", 51),  # held by fallback, equal to raw's fallback
    )
    unlogged = rows((fallback, "DDD", "2026-08-04", 10, early))  # its batch is not in raw
    allowed = {"held_by_fallback": 1, "absent_in_v1": 1, "fallback_batch_not_in_log": 1}

    def failing(v1: pa.Table) -> list[str]:
        counts = classify(raw, v1, primary, fallback, raw_batches)
        return [p.split(":")[0] for p in verdict(counts, allowed)]

    control = classify(raw, pa.concat_tables([base, unlogged]), primary, fallback, raw_batches)
    planted = {
        "price changed in v1": (
            rows(
                (primary, "AAA", "2026-07-30", 100),
                (primary, "AAA", "2026-07-31", 98),
                (fallback, "BBB", "2026-07-31", 51),
            ),
            "value_mismatch",
        ),
        "v1 key missing from raw": (
            pa.concat_tables([base, rows((primary, "EEE", "2026-07-31", 5))]),
            "v1_key_missing_from_raw",
        ),
        "fallback row from a logged batch, no raw": (
            pa.concat_tables([base, rows((fallback, "FFF", "2026-08-20", 5))]),
            "fallback_missing_from_raw",
        ),
        "row from an unknown source": (
            pa.concat_tables([base, rows(("legacy_db", "GGG", "2026-08-20", 5))]),
            "unknown_source",
        ),
    }
    checks = {
        "control: categories exact": control
        == {
            "equal": 2,
            "held_by_fallback": 1,
            "fallback_equal": 1,
            "absent_in_v1": 1,
            "fallback_batch_not_in_log": 1,
        },
        "control passes within measured counts": verdict(control, allowed) == [],
        "an explained category above its measured count fails": verdict(
            control, {**allowed, "absent_in_v1": 0}
        )
        == ["absent_in_v1: 1 > 0 measured"],
    }
    for name, (v1, category) in planted.items():
        checks[f"planted {name}: fails as {category} only"] = failing(v1) == [category]

    # File signatures: a value moved between two dates keeps the plain sums, not the checksum.
    con = duckdb.connect()
    sig = signature("duckdb", modulus)
    con.register("h", rows((primary, "AAA", "2026-07-30", 100), (primary, "AAA", "2026-07-31", 99)))
    con.register("s", rows((primary, "AAA", "2026-07-30", 99), (primary, "AAA", "2026-07-31", 100)))
    honest = con.execute(f"select 'f' as _source_file, {sig} from h").to_arrow_table()
    swapped = con.execute(f"select 'f' as _source_file, {sig} from s").to_arrow_table()
    doubled = con.execute(
        f"select 'f' as _source_file, {sig} from (select * from h union all select * from h)"
    ).to_arrow_table()
    two_files = pa.concat_tables(
        [
            honest,
            honest.set_column(
                honest.schema.get_field_index("_source_file"), "_source_file", pa.array(["g"])
            ),
        ]
    )
    checks["file signatures: identical files give no problem"] = compare_files(honest, honest) == []
    checks["planted swap of two dates is caught by the weighted checksum"] = (
        honest["sum_close_vnd"] == swapped["sum_close_vnd"]
        and len(compare_files(honest, swapped)) == 1
    )
    checks["planted file loaded twice is caught"] = len(compare_files(honest, doubled)) == 1
    checks["planted file missing from raw is caught"] = len(compare_files(two_files, honest)) == 1

    # Latest-wins SQL, run on DuckDB: the newest pull wins and sources stay apart.
    con.register(
        "log",
        pa.table(
            {
                "_source_id": [primary, primary, fallback],
                "symbol": ["AAA"] * 3,
                "session_date": [dt.date(2026, 7, 31)] * 3,
                "_ingested_at": [early, late, early],
                "_ingest_partition": [
                    dt.date(2026, 8, 3),
                    dt.date(2026, 8, 7),
                    dt.date(2026, 8, 3),
                ],
                "_source_file": ["a", "b", "c"],
                **{c: pa.array([1, 2, 3], pa.int64()) for c in PRICE_COLUMNS},
            }
        ),
    )
    latest = con.execute(latest_sql("log") + " order by source").fetchall()
    checks["latest-wins keeps the newest pull per source"] = [(r[0], r[-1]) for r in latest] == [
        (fallback, 3),
        (primary, 2),
    ]

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
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    if args.self_test:
        return self_test()
    from google.api_core.exceptions import GoogleAPIError
    from google.auth.exceptions import GoogleAuthError

    try:
        return run()
    except (FileNotFoundError, KeyError, InputError, duckdb.IOException) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2
    except (GoogleAPIError, GoogleAuthError) as exc:
        print(f"⚪ not run: BigQuery access failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
