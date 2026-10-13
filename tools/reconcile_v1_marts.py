"""Reconcile the P2 marts against v1 (Q4, redefined in ADR-0028): exact where v2 means
the same as v1; every deliberate difference explained row by row, by its mechanism.

1. calendar (full join over both calendars): inside the observed history the sessions
   and the observed range itself are exactly v1's; outside it, a day may differ only by
   being a seeded holiday (v1 had 2026-11-24 and every 2027 weekday trading).
2. prices, per (symbol, date) of `fct_price_daily` against v1's `fct_price_daily_adj`,
   prices, volume and `is_stale`:
     - source_choice: both have the row from different sources, or only v2 has it and
       took it from the fallback (v2 chooses the primary first; v1 kept whichever source
       it fetched that day);
     - absent_in_v1: only v2 has it, from the primary, and v1's raw table never had the
       key (the P1 residual), up to the count measured in config;
     - stale_from_neighbour: same source and values, only `is_stale` differs, and the
       symbol's previous row is a source_choice row (is_stale compares with it);
     - fallback_batch_not_in_log: a v1 row written by a batch that never reached v1's
       parquet log (P1 measured one, 182 rows), so v2's raw cannot hold it;
     - dropped_after_neighbour_source_change: only v1 has it, from the primary, and the
       symbol's previous row is a source_choice row. That neighbour changes is_stale, and
       a non-stale row whose open lies outside [low, high] is dropped (v1's rule).
   Anything else - a row only v1 has, a row v2 kept that v1's raw table had, a value
   difference on the same source - fails.
3. exchange: `dim_security` against v1's `dim_security_v2`; may differ only for a
   symbol whose exchange is inferred on both sides, when either its prices differ by
   source or v1's own rule, run on v1's current prices, gives v2's answer (v1 built its
   table once, from older prices).
4. universe, per (symbol, date): a membership difference is explained when the row
   itself, or a row within the previous ADV window of non-stale rows, is explained
   by (2), or the symbol's exchange difference is explained by (3).

Per-symbol signatures are compared first; rows are fetched only for symbols that differ.

Read-only: v1's DuckDB (`read_only=True`); BigQuery marts as `sa-bi-reader` through
impersonation (it can read `marts_*` and nothing else); holidays from the seed's file.

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
import yaml

from vnmarket.common.config import REPO_ROOT, load_config, load_env, utf8_stdio

VALUE_COLUMNS = ["open_vnd", "high_vnd", "low_vnd", "close_vnd", "match_qty", "stale_int"]
PRICE_EXPLAINED = {
    "source_choice",
    "absent_in_v1",
    "stale_from_neighbour",
    "fallback_batch_not_in_log",
    "dropped_after_neighbour_source_change",
}


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
    """v2, v1: calendar_date, is_trading_day, observed. holidays: holiday_date."""
    con = duckdb.connect()
    con.register("v2", v2)
    con.register("v1", v1)
    con.register("h", holidays)
    return dict(
        con.execute("""
        select case
            when v2.calendar_date is null or v1.calendar_date is null then 'only_one_side'
            when v2.observed <> v1.observed then 'observed_range_mismatch'
            when v2.observed then
                case when v2.is_trading_day = v1.is_trading_day then 'observed_equal'
                     else 'observed_mismatch' end
            when v2.is_trading_day = v1.is_trading_day then 'rule_equal'
            when h.holiday_date is not null and not v2.is_trading_day then 'holiday_seed'
            else 'rule_mismatch'
        end, count(*)
        from v2 full join v1 on v2.calendar_date = v1.calendar_date
        left join h on h.holiday_date = coalesce(v2.calendar_date, v1.calendar_date)
        group by 1
    """).fetchall()
    )


def classify_prices(
    v2: pa.Table,
    v1: pa.Table,
    v1_raw_keys: pa.Table,
    primary: str,
    fallback: str,
    unlogged_batches: list[dt.datetime],
) -> pa.Table:
    """Return (symbol, trade_date, category) for every key of either side.
    v2: symbol, trade_date, VALUE_COLUMNS, source. v1: the same plus ingested_at.
    v1_raw_keys: symbol, trade_date. unlogged_batches: v1 batches absent from its log."""
    con = duckdb.connect()
    con.register("v2", v2)
    con.register("v1", v1)
    con.register("raw", v1_raw_keys)
    con.register(
        "unlogged",
        pa.table({"ingested_at": pa.array(unlogged_batches, pa.timestamp("us", tz="UTC"))}),
    )
    same = " and ".join(f"v2.{c} is not distinct from v1.{c}" for c in VALUE_COLUMNS)
    same_but_stale = " and ".join(
        f"v2.{c} is not distinct from v1.{c}" for c in VALUE_COLUMNS if c != "stale_int"
    )
    return con.execute(f"""
        with keyed as (
            select
                coalesce(v2.symbol, v1.symbol) as symbol,
                coalesce(v2.trade_date, v1.trade_date) as trade_date,
                case
                    when v2.symbol is not null and v1.symbol is not null and {same} then 'equal'
                    when v2.symbol is not null and v1.symbol is not null
                        and v2.source <> v1.source then 'source_choice'
                    when v1.ingested_at in (select ingested_at from unlogged)
                        then 'fallback_batch_not_in_log'
                    when v1.symbol is null and v2.source = '{fallback}' then 'source_choice'
                    when v1.symbol is null and v2.source = '{primary}' and r.symbol is null
                        then 'absent_in_v1'
                    when v2.symbol is not null and v1.symbol is not null and {same_but_stale}
                        then 'stale_only'
                    when v2.symbol is null and v1.source = '{primary}' then 'v1_only_primary'
                    else 'unexplained'
                end as category
            from v2 full join v1 on v2.symbol = v1.symbol and v2.trade_date = v1.trade_date
            left join raw as r
                on r.symbol = coalesce(v2.symbol, v1.symbol)
                and r.trade_date = coalesce(v2.trade_date, v1.trade_date)
        ),
        with_previous as (
            select *, lag(category) over (partition by symbol order by trade_date) as previous
            from keyed
        )
        select
            symbol, trade_date,
            case
                when category = 'stale_only' and previous = 'source_choice'
                    then 'stale_from_neighbour'
                when category = 'stale_only' then 'unexplained'
                when category = 'v1_only_primary' and previous = 'source_choice'
                    then 'dropped_after_neighbour_source_change'
                when category = 'v1_only_primary' then 'unexplained'
                else category
            end as category
        from with_previous
    """).to_arrow_table()


def count_by(table: pa.Table, column: str) -> dict[str, int]:
    con = duckdb.connect()
    con.register("t", table)
    return dict(con.execute(f"select {column}, count(*) from t group by 1").fetchall())


def compare_exchange(
    v2: pa.Table, v1: pa.Table, price_explained: set[str], v1_rule_now: pa.Table
) -> dict[str, int]:
    """v2, v1: symbol, exchange, exchange_is_inferred (current period). v1_rule_now:
    symbol, exchange - v1's inference rule run on v1's current prices."""
    con = duckdb.connect()
    con.register("v2", v2)
    con.register("v1", v1)
    con.register("now", v1_rule_now)
    con.register("x", pa.table({"symbol": sorted(price_explained) or [""]}))
    return dict(
        con.execute("""
        select case
            when v2.exchange is not distinct from v1.exchange then 'equal'
            when v2.exchange_is_inferred and v1.exchange_is_inferred
                and v2.symbol in (select symbol from x) then 'inferred_from_other_prices'
            when v2.exchange_is_inferred and v1.exchange_is_inferred
                and v2.exchange = n.exchange then 'v1_table_built_from_older_prices'
            else 'unexplained'
        end, count(*)
        from v2 join v1 using (symbol)
        left join now as n using (symbol)
        group by 1
    """).fetchall()
    )


def compare_universe(
    v2_in: pa.Table,
    v1_in: pa.Table,
    explained_keys: pa.Table,
    v2_tradable: pa.Table,
    window: int,
    exchange_explained: set[str],
) -> dict[str, int]:
    """v2_in, v1_in: universe keys. explained_keys: price keys explained by (2).
    v2_tradable: v2's non-stale keys (the rows an ADV window counts)."""
    con = duckdb.connect()
    for name, table in (("v2", v2_in), ("v1", v1_in), ("e", explained_keys), ("t", v2_tradable)):
        con.register(name, table)
    con.register("x", pa.table({"symbol": sorted(exchange_explained) or [""]}))
    return dict(
        con.execute(f"""
        with diff as (
            select coalesce(v2.symbol, v1.symbol) as symbol,
                   coalesce(v2.trade_date, v1.trade_date) as trade_date,
                   v2.symbol is not null and v1.symbol is not null as same
            from v2 full join v1 on v2.symbol = v1.symbol and v2.trade_date = v1.trade_date
        ),
        ranked as (
            select symbol, trade_date,
                   row_number() over (partition by symbol order by trade_date) as r
            from t
        ),
        before_key as (
            -- how many tradable rows precede each differing key
            select d.symbol, d.trade_date, count(r.r) as n_before
            from diff as d
            left join ranked as r on r.symbol = d.symbol and r.trade_date < d.trade_date
            where not d.same
            group by d.symbol, d.trade_date
        ),
        window_start as (
            -- the earliest row the key's ADV reads: `window` tradable rows back
            select b.symbol, b.trade_date, coalesce(min(r.trade_date), b.trade_date) as first_date
            from before_key as b
            left join ranked as r
                on r.symbol = b.symbol and r.r between b.n_before - {window} + 1 and b.n_before
            group by b.symbol, b.trade_date
        )
        select case
            when d.same then 'equal'
            when d.symbol in (select symbol from x) then 'exchange_inferred'
            when exists (
                select 1 from e
                where e.symbol = d.symbol and e.trade_date between w.first_date and d.trade_date
            ) then 'source_choice'
            else 'unexplained'
        end, count(*)
        from diff as d
        left join window_start as w on w.symbol = d.symbol and w.trade_date = d.trade_date
        group by 1
    """).fetchall()
    )


# --- data access (read-only) --------------------------------------------------


def run(cfg: dict, env: dict) -> int:
    from google.cloud import bigquery

    from vnmarket.common.gcp import impersonated

    rec, hist = cfg["reconcile_v1"], cfg["v1_history"]
    project = env["gcp"]["project_id"]
    duck_path = Path(env["v1"]["duckdb_path"])
    primary, fallback = hist["ohlcv"]["sources"]
    marts = f"`{project}.{rec['marts_dataset']}`"
    timeout, modulus = rec["query_timeout_seconds"], rec["checksum_modulus"]
    window = rec["adv_window_rows"]
    credentials = impersonated(
        env["el"]["marts_reader_service_account"],
        hist["oauth_scope"],
        hist["impersonation_token_seconds"],
    )
    client = bigquery.Client(project=project, credentials=credentials)

    def bq(sql: str, params: list | None = None) -> pa.Table:
        config = bigquery.QueryJobConfig(query_parameters=params or [])
        job = client.query(sql, job_config=config, timeout=timeout)
        return job.result(timeout=timeout).to_arrow(create_bqstorage_client=False)

    def symbols_param(symbols: list[str]) -> list:
        return [bigquery.ArrayQueryParameter("symbols", "STRING", symbols)]

    before = duck_path.stat().st_mtime_ns
    verdicts: dict[str, bool] = {}
    v2_prices = (
        f"select symbol, trade_date, open_vnd, high_vnd, low_vnd, close_vnd, match_qty, "
        f"cast(is_stale as int64) as stale_int, _source_id as source "
        f"from {marts}.fct_price_daily"
    )
    v1_prices = (
        "select f.symbol, cast(f.session_date as date) as trade_date, f.open_adj as open_vnd, "
        "f.high_adj as high_vnd, f.low_adj as low_vnd, f.close_adj as close_vnd, "
        "f.volume as match_qty, cast(f.is_stale as integer) as stale_int, "
        "f._source_id as source, b._ingested_at as ingested_at "
        "from fct_price_daily_adj as f left join bronze_price as b "
        "on b.symbol = f.symbol and b.session_date = f.session_date"
    )
    dbt_vars = yaml.safe_load((REPO_ROOT / "dbt" / "dbt_project.yml").read_text("utf-8"))["vars"]
    unlogged = [dt.datetime.fromisoformat(x) for x in rec["unlogged_v1_batches"]]

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
        verdicts["calendar: history exactly v1's; later differences are seeded holidays"] = set(
            cal
        ) <= {"observed_equal", "rule_equal", "holiday_seed"}

        # 2. prices
        sig_v2 = bq(
            f"select symbol, {signature('bigquery', modulus, VALUE_COLUMNS)} "
            f"from ({v2_prices}) group by 1"
        )
        sig_v1 = v1.execute(
            f"select symbol, {signature('duckdb', modulus, VALUE_COLUMNS)} "
            f"from ({v1_prices}) group by 1"
        ).to_arrow_table()
        symbols = sorted(differing_symbols(sig_v2, sig_v1, VALUE_COLUMNS))
        rows_v2 = bq(f"{v2_prices} where symbol in unnest(@symbols)", symbols_param(symbols))
        rows_v1 = v1.execute(
            f"{v1_prices} where f.symbol in (select unnest($1))", [symbols]
        ).to_arrow_table()
        raw_keys = v1.execute(
            "select symbol, cast(session_date as date) as trade_date from bronze_price "
            "where symbol in (select unnest($1))",
            [symbols],
        ).to_arrow_table()
        keys = classify_prices(rows_v2, rows_v1, raw_keys, primary, fallback, unlogged)
        prices = count_by(keys, "category")
        print(
            f"     prices: {len(sig_v2) - len(symbols):,} symbols identical by signature; "
            f"{len(symbols)} compared row by row: {prices}"
        )
        caps = rec["allowed_residuals"]
        verdicts["prices and is_stale: every difference explained by its mechanism"] = (
            set(prices) <= {"equal"} | PRICE_EXPLAINED
            and prices.get("absent_in_v1", 0) <= caps["absent_in_v1"]
            and prices.get("fallback_batch_not_in_log", 0) <= caps["fallback_batch_not_in_log"]
        )
        con = duckdb.connect()
        con.register("k", keys)
        explained_keys = con.execute(
            "select symbol, trade_date from k where category in "
            "('source_choice', 'absent_in_v1', 'stale_from_neighbour', "
            "'fallback_batch_not_in_log', 'dropped_after_neighbour_source_change')"
        ).to_arrow_table()
        price_explained = {r["symbol"] for r in explained_keys.to_pylist()}

        # 3. exchange
        ex_v2 = bq(
            f"select symbol, exchange, exchange_is_inferred from {marts}.dim_security "
            "where effective_from is null"
        )
        ex_v1 = v1.execute(
            "select symbol, exchange, coalesce(exchange_is_inferred, false) "
            "as exchange_is_inferred from dim_security_v2"
        ).to_arrow_table()
        low = dbt_vars["inference_low_price_below_vnd"]
        mid = dbt_vars["inference_mid_price_max_vnd"]
        tick = dbt_vars["inference_hnx_tick_vnd"]
        min_rows = dbt_vars["exchange_inference_min_rows"]
        share = dbt_vars["exchange_inference_hnx_share"]
        v1_rule_now = v1.execute(
            f"with c as (select symbol, "
            f"count(*) filter (where close_vnd < {low}) as n_low, "
            f"count(*) filter (where close_vnd < {low} and close_vnd % {tick} = 0) as l100, "
            f"count(*) filter (where close_vnd between {low} and {mid}) as n_mid, "
            f"count(*) filter (where close_vnd between {low} and {mid} "
            f"and close_vnd % {tick} = 0) as m100 from bronze_price group by symbol) "
            f"select symbol, case "
            f"when n_low >= {min_rows} then case when l100 > {share} * n_low "
            f"then 'HNX' else 'HOSE' end "
            f"when n_mid >= {min_rows} then case when m100 > {share} * n_mid "
            f"then 'HNX' else 'HOSE' end end as exchange from c"
        ).to_arrow_table()
        exchange = compare_exchange(ex_v2, ex_v1, price_explained, v1_rule_now)
        print(f"     exchange: {exchange}")
        verdicts["exchange equal except inferred from other or newer prices"] = (
            "unexplained" not in exchange
        )
        con.register("ev2", ex_v2)
        con.register("ev1", ex_v1)
        changed = con.execute(
            "select ev2.symbol from ev2 join ev1 using (symbol) "
            "where ev2.exchange is distinct from ev1.exchange"
        ).fetchall()
        exchange_explained = {s for (s,) in changed} & price_explained

        # 4. universe
        uni_v2 = f"select symbol, trade_date from {marts}.fct_universe_daily where is_in_universe"
        uni_v1 = "select symbol, cast(session_date as date) as trade_date from v_universe"
        usig_v2 = bq(
            f"select symbol, {signature('bigquery', modulus, [])} from ({uni_v2}) group by 1"
        )
        usig_v1 = v1.execute(
            f"select symbol, {signature('duckdb', modulus, [])} from ({uni_v1}) group by 1"
        ).to_arrow_table()
        usymbols = sorted(differing_symbols(usig_v2, usig_v1, []))
        urows_v2 = bq(f"{uni_v2} and symbol in unnest(@symbols)", symbols_param(usymbols))
        urows_v1 = v1.execute(
            f"{uni_v1} where symbol in (select unnest($1))", [usymbols]
        ).to_arrow_table()
        tradable = bq(
            f"select symbol, trade_date from {marts}.fct_price_daily "
            "where is_stale = false and symbol in unnest(@symbols)",
            symbols_param(usymbols),
        )
        universe = compare_universe(
            urows_v2, urows_v1, explained_keys, tradable, window, exchange_explained
        )
        print(
            f"     universe: {len(usig_v2) - len(usymbols):,} symbols identical; "
            f"{len(usymbols)} compared row by row: {universe}"
        )
        verdicts["universe: every difference within an explained ADV window or exchange"] = (
            "unexplained" not in universe
        )

    verdicts["v1's DuckDB unchanged during the run"] = duck_path.stat().st_mtime_ns == before
    for name, ok in verdicts.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(verdicts.values()) else 1


def self_test() -> int:
    """Known answers on synthetic tables; each planted fault fails exactly its own check."""
    d = dt.date.fromisoformat
    p, f = "primary", "fallback"

    def prices(*rows: tuple) -> pa.Table:
        """rows: (symbol, date, close, source[, stale])"""
        rows = [r if len(r) == 5 else (*r, 0) for r in rows]
        symbol, date, close, source, stale = zip(*rows, strict=True)
        n = len(rows)
        return pa.table(
            {
                "symbol": list(symbol),
                "trade_date": [d(x) for x in date],
                **{
                    c: pa.array([1] * n, pa.int64())
                    for c in VALUE_COLUMNS
                    if c not in ("close_vnd", "stale_int")
                },
                "close_vnd": pa.array(close, pa.int64()),
                "stale_int": pa.array(stale, pa.int64()),
                "source": list(source),
            }
        )

    def keys(*rows: tuple) -> pa.Table:
        return pa.table({"symbol": [r[0] for r in rows], "trade_date": [d(r[1]) for r in rows]})

    batch = dt.datetime(2026, 8, 6, 4, 40, 36, tzinfo=dt.UTC)
    earlier = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)

    def classes(v2_rows: pa.Table, v1_rows: pa.Table, raw_rows: pa.Table) -> dict[str, int]:
        if "ingested_at" not in v1_rows.column_names:
            v1_rows = v1_rows.append_column("ingested_at", pa.array([earlier] * len(v1_rows)))
        return count_by(classify_prices(v2_rows, v1_rows, raw_rows, p, f, [batch]), "category")

    v1 = prices(
        ("A", "2026-01-05", 10, p), ("B", "2026-01-05", 20, f), ("B", "2026-01-06", 21, p, 1)
    )
    v2 = prices(
        ("A", "2026-01-05", 10, p),
        ("B", "2026-01-05", 19, p),
        ("B", "2026-01-06", 21, p, 0),
        ("C", "2026-01-05", 7, f),
        ("D", "2026-01-05", 8, p),
    )
    raw = keys(("A", "2026-01-05"), ("B", "2026-01-05"), ("B", "2026-01-06"))
    control = classes(v2, v1, raw)
    one_a = prices(("A", "2026-01-05", 10, p))
    # A drop-rule regression: v2 keeps a primary row whose key v1's raw table had.
    kept_bad = classes(
        prices(("A", "2026-01-05", 10, p), ("E", "2026-01-05", 5, p)),
        one_a,
        keys(("A", "2026-01-05"), ("E", "2026-01-05")),
    )
    lost_row = classes(one_a, prices(("A", "2026-01-05", 10, p), ("A", "2026-01-06", 11, p)), raw)
    same_source_change = classes(prices(("A", "2026-01-05", 12, p)), one_a, raw)
    lonely_stale = classes(prices(("A", "2026-01-05", 10, p, 1)), one_a, raw)
    v1_extra = prices(("A", "2026-01-05", 10, p), ("H", "2026-08-04", 9, f))

    def stamped(when: dt.datetime) -> pa.Table:
        return v1_extra.append_column("ingested_at", pa.array([earlier, when]))

    unlogged_row = classes(one_a, stamped(batch), raw)
    # ABR 2019-08-22: the day before came from the fallback in v2, so v2's row is not
    # stale, its open lies outside [low, high] and it is dropped; v1 kept it as stale.
    neighbour_drop = classes(
        prices(("J", "2019-08-21", 13273, f)),
        prices(("J", "2019-08-21", 15000, p), ("J", "2019-08-22", 15000, p, 1)),
        keys(("J", "2019-08-21"), ("J", "2019-08-22")),
    )
    logged_row = classes(one_a, stamped(dt.datetime(2026, 8, 18, tzinfo=dt.UTC)), raw)

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
            [("2026-10-13", True, False), ("2026-11-24", False, False), ("2026-11-26", True, False)]
        ),
        v1_cal,
        holidays,
    )

    explained = keys(("B", "2026-01-05"))
    tradable = keys(
        ("B", "2026-01-02"),
        ("B", "2026-01-05"),
        ("B", "2026-01-06"),
        ("B", "2026-01-07"),
        ("B", "2026-01-08"),
        ("F", "2026-01-08"),
    )
    u_control = compare_universe(
        keys(("A", "2026-01-05"), ("B", "2026-01-06")),
        keys(("A", "2026-01-05"), ("G", "2026-01-06")),
        explained,
        tradable,
        2,
        {"G"},
    )
    # B on 2026-01-08 reads 01-06 and 01-07 only: the explained 01-05 row is out of reach.
    u_outside = compare_universe(
        keys(("A", "2026-01-05"), ("B", "2026-01-08")),
        keys(("A", "2026-01-05")),
        explained,
        tradable,
        2,
        set(),
    )

    ex_v2 = pa.table(
        {
            "symbol": ["A", "B", "C"],
            "exchange": ["HOSE", "HNX", "HNX"],
            "exchange_is_inferred": [False, True, True],
        }
    )
    ex_v1 = pa.table(
        {
            "symbol": ["A", "B", "C"],
            "exchange": ["HOSE", "HOSE", "HOSE"],
            "exchange_is_inferred": [False, True, True],
        }
    )

    checks = {
        "control prices: each difference has its mechanism": control
        == {
            "equal": 1,
            "source_choice": 2,
            "stale_from_neighbour": 1,
            "absent_in_v1": 1,
        },
        "planted: v2 keeps a row v1's raw had (drop-rule regression) - unexplained": kept_bad
        == {"equal": 1, "unexplained": 1},
        "planted: a row only v1 has - unexplained": lost_row == {"equal": 1, "unexplained": 1},
        "planted: same source, different price - unexplained": same_source_change
        == {"unexplained": 1},
        "planted: is_stale differs with no source change before it - unexplained": lonely_stale
        == {"unexplained": 1},
        "a v1 row from the batch missing from the log is explained": unlogged_row
        == {"equal": 1, "fallback_batch_not_in_log": 1},
        "planted: the same row from a logged batch - unexplained": logged_row
        == {"equal": 1, "unexplained": 1},
        "a v1-only primary row after a source change is explained": neighbour_drop
        == {"source_choice": 1, "dropped_after_neighbour_source_change": 1},
        "control calendar": cal_control
        == {"observed_equal": 1, "holiday_seed": 1, "rule_equal": 1},
        "planted calendar: observed range moved, days on one side only": cal_planted
        == {"observed_range_mismatch": 1, "holiday_seed": 1, "only_one_side": 2},
        "control universe: within the ADV window, or the exchange explained": u_control
        == {"equal": 1, "source_choice": 1, "exchange_inferred": 1},
        "planted universe difference outside the ADV window - unexplained": u_outside
        == {"equal": 1, "unexplained": 1},
        "exchange: an inferred difference is explained only with other prices": compare_exchange(
            ex_v2, ex_v1, {"B"}, pa.table({"symbol": ["C"], "exchange": ["HOSE"]})
        )
        == {"equal": 1, "inferred_from_other_prices": 1, "unexplained": 1},
        "exchange: v1's rule on v1's current prices agrees with v2 - explained": compare_exchange(
            ex_v2, ex_v1, {"B"}, pa.table({"symbol": ["C"], "exchange": ["HNX"]})
        )
        == {"equal": 1, "inferred_from_other_prices": 1, "v1_table_built_from_older_prices": 1},
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

    try:  # only configuration and access problems are "not run"; a code bug raises
        cfg, env = load_config("el"), load_env()
        return run(cfg, env)
    except FileNotFoundError as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2
    except duckdb.IOException as exc:
        print(f"⚪ not run: v1's DuckDB is not readable (its daily job?): {exc}", file=sys.stderr)
        return 2
    except (GoogleAPIError, GoogleAuthError) as exc:
        print(f"⚪ not run: BigQuery access failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
