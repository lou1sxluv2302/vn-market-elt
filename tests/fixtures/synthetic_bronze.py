"""Seeded generator of a synthetic v1 bronze tree for self-tests. No real market data.

Writes, under a given root, the same layout as v1's `data/bronze`:
source=<s>/dataset=ohlcv_daily/ingest_date=<d>/*.parquet plus flat reference
files and daily flow files under source=vnstock_data/. Each call with the same seed writes the same
bytes, so self-tests have known answers.
"""

from __future__ import annotations

import datetime as dt
import random
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

INGESTED_AT = {  # one timestamp per pull
    "2026-08-03": dt.datetime(2026, 8, 3, 9, 0, tzinfo=dt.UTC),
    "2026-08-07": dt.datetime(2026, 8, 7, 9, 0, tzinfo=dt.UTC),
    "2026-09-01": dt.datetime(2026, 9, 1, 9, 0, tzinfo=dt.UTC),
}


def ohlcv(source: str, ingest_date: str, rows: list[tuple[str, str, int]]) -> pa.Table:
    """rows: (symbol, session_date, close_vnd); other prices derive from close."""
    symbols, dates, closes = zip(*rows, strict=True) if rows else ((), (), ())
    closes = list(closes)
    n = len(closes)
    return pa.table(
        {
            "symbol": pa.array(list(symbols), pa.string()),
            "session_date": pa.array([dt.date.fromisoformat(d) for d in dates], pa.date32()),
            "open_vnd": pa.array([c - 100 for c in closes], pa.int64()),
            "high_vnd": pa.array([c + 200 for c in closes], pa.int64()),
            "low_vnd": pa.array([c - 200 for c in closes], pa.int64()),
            "close_vnd": pa.array(closes, pa.int64()),
            "volume": pa.array([1_000 + i for i in range(n)], pa.int64()),
            "_source_id": pa.array([source] * n, pa.string()),
            "_batch_id": pa.array([f"{source}-{ingest_date}"] * n, pa.string()),
            "_ingested_at": pa.array([INGESTED_AT[ingest_date]] * n, pa.timestamp("us", tz="UTC")),
            "_payload_hash": pa.array([f"h{i}" for i in range(n)], pa.string()),
        }
    )


def flows(rows: list[tuple[str, str, float]]) -> pa.Table:
    """A flow file: (symbol, session_date, net value); v1's real files carry many more columns."""
    symbols, dates, values = zip(*rows, strict=True) if rows else ((), (), ())
    return pa.table(
        {
            "symbol": pa.array(list(symbols), pa.string()),
            "session_date": pa.array([dt.date.fromisoformat(d) for d in dates], pa.date32()),
            "net_val_total": pa.array(list(values), pa.float64()),
        }
    )


def index_table(rows: list[tuple[str, str, float]]) -> pa.Table:
    """v1's index table shape, sorted by key: (index_code, session_date, close)."""
    rows = sorted(rows)
    codes, dates, closes = zip(*rows, strict=True) if rows else ((), (), ())
    return pa.table(
        {
            "index_code": pa.array(list(codes), pa.string()),
            "session_date": pa.array([dt.date.fromisoformat(d) for d in dates], pa.date32()),
            "close": pa.array(list(closes), pa.float64()),
        }
    )


def write(path: Path, table: pa.Table) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return path


def bronze_tree(
    root: Path,
    primary: str,
    fallback: str,
    reference_files: list[str],
    flow_files: list[str],
    fundamental_files: tuple[str, ...] | list[str] = (),
    seed: int = 7,
) -> dict:
    """Write the standard synthetic tree; return paths the tests plant faults next to."""
    rng = random.Random(seed)  # noqa: S311 - reproducible test data, not security
    part = "dataset=ohlcv_daily"

    def ohlcv_path(source: str, date: str, name: str) -> Path:
        return root / f"source={source}" / part / f"ingest_date={date}" / name

    base = [("AAA", "2026-07-30", 10_000), ("AAA", "2026-07-31", 10_100)]
    write(ohlcv_path(primary, "2026-08-03", "a.parquet"), ohlcv(primary, "2026-08-03", base))
    # The same key in a later pull, re-adjusted: raw keeps both.
    write(
        ohlcv_path(primary, "2026-08-07", "b.parquet"),
        ohlcv(
            primary,
            "2026-08-07",
            [("AAA", "2026-07-31", 9_900), ("BBB", "2026-07-31", 5_000 + rng.randint(0, 99))],
        ),
    )
    write(
        ohlcv_path(fallback, "2026-08-07", "c.parquet"),
        ohlcv(fallback, "2026-08-07", [("CCC", "2026-07-31", 7_000)]),
    )
    late = write(
        ohlcv_path(primary, "2026-09-01", "d.parquet"),
        ohlcv(primary, "2026-09-01", [("AAA", "2026-08-29", 10_500)]),
    )
    ref_dir = root / "source=vnstock_data"
    for name in reference_files:
        write(ref_dir / f"{name}.parquet", pa.table({"symbol": ["AAA", "BBB"]}))
    flow_paths = {
        name: write(
            ref_dir / f"{name}.parquet",
            flows([("AAA", "2026-07-30", 1.5), ("BBB", "2026-07-31", -2.0)]),
        )
        for name in flow_files
    }
    for name in fundamental_files:
        write(
            ref_dir / f"{name}.parquet",
            pa.table({"symbol": ["AAA", "BBB"], "value": [1.0, 0.0]}),
        )
    return {
        "flows": flow_paths,
        "late": late,
        "first_partition": late.parent.parent / "ingest_date=2026-08-03",
        "reference_dir": ref_dir,
        "ohlcv_dir": root / f"source={primary}" / part,
    }
