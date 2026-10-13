"""Reconcile the P2 marts against v1 (Q4, redefined): exact where v2 means the same as
v1, every deliberate difference counted in its own category.

1. calendar: the observed sessions (history) are exactly v1's; after the observed range,
   every day where the two calendars disagree is a date of the holiday seed (v1 knew no
   2026-11-24 and no 2027 holidays). Anything else fails.
2. prices: `fct_price_daily` against v1's `fct_price_daily_adj`, per (symbol, date),
   prices, volume and `is_stale`. v2 chooses the primary source first where v1 kept
   whichever source it fetched that day, so a symbol is "touched" when any of its keys
   comes from a different source or exists on one side only. Differences inside touched
   symbols are counted as `source_choice`; any difference in an untouched symbol fails.
3. universe: `fct_universe_daily.is_in_universe` against v1's `v_universe` membership.
   Differences are explained when the symbol is touched (its turnover history differs)
   or its exchange differs between the two security tables; otherwise they fail.

Per-symbol signatures (count, sums, date-weighted checksums) are compared first; rows
are fetched only for symbols whose signature differs.

Read-only: v1's DuckDB (`read_only=True`); BigQuery marts as `sa-bi-reader` through
impersonation (it can read `marts_*` and nothing else).

Exit codes: 0 = all checks pass · 1 = a check fails · 2 = usage, config or access error.

Usage:
    python tools/reconcile_v1_marts.py
    python tools/reconcile_v1_marts.py --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

import duckdb
import pyarrow as pa

from vnmarket.common.config import REPO_ROOT, load_config, load_env, utf8_stdio

VALUE_COLUMNS = ["open_vnd", "high_vnd", "low_vnd", "close_vnd", "match_qty", "stale_int"]


# --- SQL shared by BigQuery and DuckDB ----------------------------------------


def signature(dialect: str, modulus: int, columns: list[str]) -> str:
    """Aggregate signature over rows with a `trade_date` column."""
    day = (
        "unix_date(trade_date)"
        if dialect == "bigquery"
        else "date_diff('day', date '1970-01-01', trade_date)"
    )
    weight = f"(mod({day}, {modulus}) + 1)"
    parts = ["count(*) as n", f"sum({day}) as sum_day"]
    for c in columns:
        parts += [f"sum({c}) as sum_{c}", f"sum({c} * {weight}) as wsum_{c}"]
    return ", ".join(parts)


def signature_columns(columns: list[str]) -> list[str]:
    return ["n", "sum_day"] + [f"{k}_{c}" for c in columns for k in ("sum", "wsum")]


def differing_symbols(a: pa.Table, b: pa.Table, columns: list[str]) -> set[str]:
    con = duckdb.connect()
    con.register("a", a)
    con.register("b", b)
    unequal = " or ".join(f"a.{c} is distinct from b.{c}" for c in signature_columns(columns))
    rows = con.execute(
        f"select coalesce(a.symbol, b.symbol) from a full join b on a.symbol = b.symbol "
        f"where {unequal}"
    ).fetchall()
    return {s for (s,) in rows}


# --- comparison logic (pure: arrow tables in, verdicts out) -------------------


def compare_calendar(v2: pa.Table, v1: pa.Table, holidays: pa.Table) -> dict[str, int]:
    """v2, v1: calendar_date, is_trading_day, observed (bool). holidays: holiday_date."""
    con = duckdb.connect()
    con.register("v2", v2)
    con.register("v1", v1)
    con.register("h", holidays)
    return dict(
        con.execute("""
        select case
            when v2.observed and v1.observed then
                case when v2.is_trading_day = v1.is_trading_day then 'observed_equal'
                     else 'observed_mismatch' end
            when v2.is_trading_day is not distinct from v1.is_trading_day then 'rule_equal'
            when h.holiday_date is not null and not v2.is_trading_day then 'holiday_seed'
            else 'rule_mismatch'
        end as category, count(*)
        from v2 join v1 using (calendar_date)
        left join h on h.holiday_date = v2.calendar_date
        group by 1
    """).fetchall()
    )


def compare_prices(v2: pa.Table, v1: pa.Table) -> tuple[dict[str, int], set[str]]:
    """v2, v1: symbol, trade_date, VALUE_COLUMNS, source. Returns (categories, touched)."""
    con = duckdb.connect()
    con.register("v2", v2)
    con.register("v1", v1)
    con.execute(
        """
        create temp table keyed as
        select coalesce(v2.symbol, v1.symbol) as symbol,
               v2.symbol is not null as in_v2, v1.symbol is not null as in_v1,
               v2.source as v2_source, v1.source as v1_source,
               ("""
        + " and ".join(f"v2.{c} is not distinct from v1.{c}" for c in VALUE_COLUMNS)
        + """) as same_values
        from v2 full join v1 on v2.symbol = v1.symbol and v2.trade_date = v1.trade_date
    """
    )
    touched = {
        s
        for (s,) in con.execute("""
        select distinct symbol from keyed
        where not (in_v2 and in_v1) or v2_source is distinct from v1_source
    """).fetchall()
    }
    con.register("t", pa.table({"symbol": sorted(touched) or [""]}))
    counts = dict(
        con.execute("""
        select case
            when in_v2 and in_v1 and same_values then 'equal'
            when symbol in (select symbol from t) then 'source_choice'
            else 'unexplained'
        end, count(*)
        from keyed group by 1
    """).fetchall()
    )
    return counts, touched


def compare_universe(
    v2: pa.Table, v1: pa.Table, touched: set[str], exchange_differs: set[str]
) -> dict[str, int]:
    """v2, v1: symbol, trade_date of rows in the universe."""
    con = duckdb.connect()
    con.register("v2", v2)
    con.register("v1", v1)
    con.register("t", pa.table({"symbol": sorted(touched) or [""]}))
    con.register("x", pa.table({"symbol": sorted(exchange_differs) or [""]}))
    return dict(
        con.execute("""
        select case
            when v2.symbol is not null and v1.symbol is not null then 'equal'
            when coalesce(v2.symbol, v1.symbol) in (select symbol from t) then 'source_choice'
            when coalesce(v2.symbol, v1.symbol) in (select symbol from x) then 'exchange_differs'
            else 'unexplained'
        end, count(*)
        from v2 full join v1 on v2.symbol = v1.symbol and v2.trade_date = v1.trade_date
        group by 1
    """).fetchall()
    )


# --- data access (read-only) --------------------------------------------------


def run() -> int:
    from google.cloud import bigquery

    from vnmarket.common.gcp import impersonated

    cfg = load_config("el")
    rec = cfg["reconcile_v1"]
    env = load_env()
    project = env["gcp"]["project_id"]
    duck_path = Path(env["v1"]["duckdb_path"])
    marts = f"`{project}.{rec['marts_dataset']}`"
    timeout, modulus = rec["query_timeout_seconds"], rec["checksum_modulus"]
    credentials = impersonated(
        env["el"]["marts_reader_service_account"],
        cfg["v1_history"]["oauth_scope"],
        cfg["v1_history"]["impersonation_token_seconds"],
    )
    client = bigquery.Client(project=project, credentials=credentials)

    def bq(sql: str, params: list | None = None) -> pa.Table:
        config = bigquery.QueryJobConfig(query_parameters=params or [])
        job = client.query(sql, job_config=config, timeout=timeout)
        return job.result(timeout=timeout).to_arrow(create_bqstorage_client=False)

    before = duck_path.stat().st_mtime_ns
    verdicts: dict[str, bool] = {}
    v2_prices = (
        f"select symbol, trade_date, open_vnd, high_vnd, low_vnd, close_vnd, match_qty, "
        f"cast(is_stale as int64) as stale_int, _source_id as source "
        f"from {marts}.fct_price_daily"
    )
    v1_prices = (
        "select symbol, cast(session_date as date) as trade_date, open_adj as open_vnd, "
        "high_adj as high_vnd, low_adj as low_vnd, close_adj as close_vnd, volume as match_qty, "
        "cast(is_stale as integer) as stale_int, _source_id as source from fct_price_daily_adj"
    )

    with duckdb.connect(str(duck_path), read_only=True) as v1:
        # 1. calendar
        v2_cal = bq(
            f"select calendar_date, is_trading_day, calendar_source = 'observed' as observed "
            f"from {marts}.dim_trading_calendar"
        )
        v1_cal = v1.execute(
            "select cast(calendar_date as date) as calendar_date, is_trading_day, "
            "calendar_source = 'observed_data' as observed from dim_trading_calendar"
        ).to_arrow_table()
        # The seed's own file: sa-bi-reader cannot read the staging dataset, and the
        # CSV is the source the seed is built from.
        holidays = (
            duckdb.connect()
            .execute(
                "select cast(holiday_date as date) as holiday_date from read_csv_auto($1)",
                [str(REPO_ROOT / "dbt" / "seeds" / "holidays.csv")],
            )
            .to_arrow_table()
        )
        cal = compare_calendar(v2_cal, v1_cal, holidays)
        print(f"     calendar: {cal}")
        verdicts["calendar: observed sessions equal; later differences are seeded holidays"] = not {
            "observed_mismatch",
            "rule_mismatch",
        } & set(cal)

        # 2. prices: signatures per symbol, rows for the symbols that differ
        sig_v2 = bq(
            f"select symbol, {signature('bigquery', modulus, VALUE_COLUMNS)} "
            f"from ({v2_prices}) group by 1"
        )
        sig_v1 = v1.execute(
            f"select symbol, {signature('duckdb', modulus, VALUE_COLUMNS)} "
            f"from ({v1_prices}) group by 1"
        ).to_arrow_table()
        symbols = sorted(differing_symbols(sig_v2, sig_v1, VALUE_COLUMNS))
        param = [bigquery.ArrayQueryParameter("symbols", "STRING", symbols)]
        rows_v2 = bq(f"{v2_prices} where symbol in unnest(@symbols)", param)
        rows_v1 = v1.execute(
            f"{v1_prices} where symbol in (select unnest($1))", [symbols]
        ).to_arrow_table()
        prices, touched = compare_prices(rows_v2, rows_v1)
        print(
            f"     prices: {len(sig_v2) - len(symbols):,} symbols identical by signature; "
            f"{len(symbols)} compared row by row: {prices}; touched symbols: {len(touched)}"
        )
        verdicts["prices and is_stale equal except where v2 chose another source"] = (
            "unexplained" not in prices
        )

        # 3. universe
        uni_v2 = f"select symbol, trade_date from {marts}.fct_universe_daily where is_in_universe"
        uni_v1 = "select symbol, cast(session_date as date) as trade_date from v_universe"
        usig_v2 = bq(
            f"select symbol, {signature('bigquery', modulus, [])} from ({uni_v2}) group by 1"
        )
        usig_v1 = v1.execute(
            f"select symbol, {signature('duckdb', modulus, [])} from ({uni_v1}) group by 1"
        ).to_arrow_table()
        usymbols = sorted(differing_symbols(usig_v2, usig_v1, []))
        exchanges_v2 = bq(
            f"select distinct symbol, exchange from {marts}.dim_security "
            "where effective_from is null"
        )
        exchanges_v1 = v1.execute("select symbol, exchange from dim_security_v2").to_arrow_table()
        con = duckdb.connect()
        con.register("a", exchanges_v2)
        con.register("b", exchanges_v1)
        exchange_differs = {
            s
            for (s,) in con.execute(
                "select a.symbol from a join b using (symbol) "
                "where a.exchange is distinct from b.exchange"
            ).fetchall()
        }
        uparam = [bigquery.ArrayQueryParameter("symbols", "STRING", usymbols)]
        urows_v2 = bq(f"{uni_v2} and symbol in unnest(@symbols)", uparam)
        urows_v1 = v1.execute(
            f"{uni_v1} where symbol in (select unnest($1))", [usymbols]
        ).to_arrow_table()
        universe = compare_universe(urows_v2, urows_v1, touched, exchange_differs)
        print(
            f"     universe: {len(usig_v2) - len(usymbols):,} symbols identical; "
            f"{len(usymbols)} compared row by row: {universe}; "
            f"exchange differs for {len(exchange_differs)} symbols"
        )
        verdicts["universe equal except source choice or a different exchange"] = (
            "unexplained" not in universe
        )

    verdicts["v1's DuckDB unchanged during the run"] = duck_path.stat().st_mtime_ns == before
    for name, ok in verdicts.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(verdicts.values()) else 1


def self_test() -> int:
    """Known answers on synthetic tables; each planted fault fails exactly its own check."""
    d = dt.date.fromisoformat

    def prices(*rows: tuple) -> pa.Table:
        """rows: (symbol, date, close, source)"""
        symbol, date, close, source = zip(*rows, strict=True)
        n = len(rows)
        return pa.table(
            {
                "symbol": list(symbol),
                "trade_date": [d(x) for x in date],
                **{c: pa.array([1] * n, pa.int64()) for c in VALUE_COLUMNS if c != "close_vnd"},
                "close_vnd": pa.array(close, pa.int64()),
                "source": list(source),
            }
        )

    v1 = prices(
        ("A", "2026-01-05", 10, "p"),
        ("A", "2026-01-06", 11, "p"),
        ("B", "2026-01-05", 20, "f"),
        ("B", "2026-01-06", 21, "p"),
    )
    v2 = prices(
        ("A", "2026-01-05", 10, "p"),
        ("A", "2026-01-06", 11, "p"),
        ("B", "2026-01-05", 19, "p"),
        ("B", "2026-01-06", 22, "p"),
    )
    control, touched = compare_prices(v2, v1)
    planted, _ = compare_prices(
        prices(("A", "2026-01-05", 10, "p"), ("A", "2026-01-06", 12, "p")),
        v1.slice(0, 2),
    )

    def cal(rows: list) -> pa.Table:
        dates, trading, observed = zip(*rows, strict=True)
        return pa.table(
            {
                "calendar_date": [d(x) for x in dates],
                "is_trading_day": list(trading),
                "observed": list(observed),
            }
        )

    holidays = pa.table({"holiday_date": [d("2026-11-24")]})
    v1_cal = cal(
        [("2026-10-13", True, True), ("2026-11-24", True, False), ("2026-11-25", True, False)]
    )
    cal_control = compare_calendar(
        cal(
            [("2026-10-13", True, True), ("2026-11-24", False, False), ("2026-11-25", True, False)]
        ),
        v1_cal,
        holidays,
    )
    cal_planted = compare_calendar(
        cal(
            [
                ("2026-10-13", False, True),
                ("2026-11-24", False, False),
                ("2026-11-25", False, False),
            ]
        ),
        v1_cal,
        holidays,
    )

    def uni(*rows: tuple) -> pa.Table:
        return pa.table({"symbol": [r[0] for r in rows], "trade_date": [d(r[1]) for r in rows]})

    u_control = compare_universe(
        uni(("A", "2026-01-05"), ("B", "2026-01-06")),
        uni(("A", "2026-01-05"), ("C", "2026-01-06")),
        {"B"},
        {"C"},
    )
    u_planted = compare_universe(
        uni(("A", "2026-01-05")), uni(("A", "2026-01-05"), ("D", "2026-01-06")), set(), set()
    )

    checks = {
        "control prices: B touched by source choice, A equal": (
            control == {"equal": 2, "source_choice": 2} and touched == {"B"}
        ),
        "planted price change in an untouched symbol is unexplained only": planted
        == {"equal": 1, "unexplained": 1},
        "control calendar: observed equal, 2026-11-24 a seeded holiday": cal_control
        == {"observed_equal": 1, "holiday_seed": 1, "rule_equal": 1},
        "planted calendar faults: an observed session and an unseeded day": cal_planted
        == {"observed_mismatch": 1, "holiday_seed": 1, "rule_mismatch": 1},
        "control universe: differences explained by source or exchange": u_control
        == {"equal": 1, "source_choice": 1, "exchange_differs": 1},
        "planted universe row with no explanation is unexplained": u_planted
        == {"equal": 1, "unexplained": 1},
        "signatures: identical tables differ nowhere": differing_symbols(
            pa.table({"symbol": ["A"], "n": [1], "sum_day": [5]}),
            pa.table({"symbol": ["A"], "n": [1], "sum_day": [5]}),
            [],
        )
        == set(),
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
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    if args.self_test:
        return self_test()
    from google.api_core.exceptions import GoogleAPIError
    from google.auth.exceptions import GoogleAuthError

    try:
        return run()
    except (FileNotFoundError, KeyError, duckdb.Error) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2
    except (GoogleAPIError, GoogleAuthError) as exc:
        print(f"⚪ not run: BigQuery access failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
