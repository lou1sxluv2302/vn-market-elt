"""Prove that every dbt data test can go red: plant one fault at a time in a synthetic warehouse.

A data test that has never failed proves nothing (docs/engineering-rules.md; P3 is done
when every test has failed at least once). This builds the dbt project on DuckDB from a
synthetic fixture with known answers, then:
- control: the clean build, every data test passes;
- each fault: the same build with one fault planted - raw rows changed, one model's SQL
  mutated, a seed edited, a variable in the wrong unit, or raw loaded after the build -
  and the set of red tests must equal the fault's expected set exactly. Most sets hold one
  test; a defect that dbt carries downstream (a duplicated key) lists its echoes by name;
- coverage: every data test in the manifest is red in at least one fault. dbt's built-in
  generic tests are exempt (engineering-rules escape) unless a fault names them.
Red is read from target/run_results.json, never from printed text.

The fixture is generated here (no market data in the repository): 50 listed symbols and two
delisted ones over 65 sessions of 2026, plus a known bad date, a Saturday pull and a
partial pull after the last session. It moves the seeded HNX -> HOSE date into its range so
the exchange history is exercised.

Exit codes: 0 = control green, every fault red exactly as expected, every test covered ·
1 = a mismatch or an uncovered test · 2 = cannot run (no dbt, a mutation no longer
applies, a dbt step crashed or timed out).

Usage:
    python tools/planted_faults.py [--fault NAME ...] [--list] [--keep DIR]
    python tools/planted_faults.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import io
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import yaml

from vnmarket.common.config import REPO_ROOT, load_config, utf8_stdio
from vnmarket.common.process import Timeout, run_bounded

DBT_DIR = REPO_ROOT / "dbt"
STEP_TIMEOUT_SECONDS = load_config("dq")["planted_faults"]["dbt_step_timeout_seconds"]
BUILTIN_TESTS = {"unique", "not_null", "accepted_values", "relationships"}
RED = {"fail", "error", "warn"}
# The dbt project's own values, read rather than copied.
DBT_VARS = yaml.safe_load((DBT_DIR / "dbt_project.yml").read_text("utf-8"))["vars"]
PRIMARY, FALLBACK = DBT_VARS["primary_price_source"], DBT_VARS["fallback_price_source"]
MIN_TRADED = DBT_VARS["min_traded_symbols_per_session"]
SEED_TESTS = yaml.safe_load((DBT_DIR / "seeds" / "_seeds.yml").read_text("utf-8"))["seeds"]

# --- the synthetic fixture ------------------------------------------------------------

HOLIDAYS = {dt.date(2026, 2, d) for d in range(16, 21)}
SESSIONS = [
    d
    for d in (dt.date(2026, 1, 5) + dt.timedelta(days=i) for i in range(96))
    if d.weekday() < 5 and d not in HOLIDAYS
]
BAD_DATE = dt.date(2018, 7, 23)  # the known_bad_dates seed
SATURDAY = dt.date(2026, 3, 7)
PARTIAL_DAY = SESSIONS[-1] + dt.timedelta(days=3)  # the Monday after the last session
MOVE_DATE = "2026-03-02"  # fixture date of the seeded HNX -> HOSE move
PULLED_AT = "2026-04-11 09:00:00+00"
OLDER_PULL_AT = "2026-03-01 09:00:00+00"

HOSE = [f"S{k:02d}" for k in range(1, 21)]
HNX = [f"S{k:02d}" for k in range(21, 41)]
LATE = [f"S{k:02d}" for k in range(41, 51)]  # listed from session 10 (HOSE)
LIQUID = {"S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S21", "S22", "S23", "S24"}
STALE_EVERY_THIRD = {f"S{k:02d}" for k in [*range(11, 16), *range(31, 36)]}
HNX_WITH_HOSE_TICKS = "S40"  # adjusted prices: ticks of 10 below 10,000 VND
DELISTED_IN_LIST, NOT_IN_LIST = "D01", "D02"

FIXTURE_VARS = {
    "dq_watched_symbols": ["S01", "S02"],
    "dq_watched_from": str(SESSIONS[0]),
    "dq_watched_to": str(SESSIONS[-1]),
    "dq_falling_market_windows": [
        {"from": "2026-02-01", "to": "2026-02-28"},
        {"from": "2026-03-01", "to": "2026-03-31"},
    ],
    "dq_falling_market_symbols_more_than": 3,
    "dq_fallback_rows_ceiling": 4,  # S03 x 3 (primary missing) + S04 x 1 (primary broken)
}


def base_and_tick(symbol: str) -> tuple[int, int]:
    if symbol == HNX_WITH_HOSE_TICKS:
        return 8_000, 10
    if symbol == DELISTED_IN_LIST:
        return 5_000, 100
    if symbol in HNX:
        return 15_000, 100
    if symbol in LATE:
        return 12_000, 50
    return 20_000, 50  # HOSE and NOT_IN_LIST


def row(symbol: str, day: dt.date, o, h, lo, c, volume, source=PRIMARY, at=PULLED_AT) -> dict:
    return {
        "symbol": symbol,
        "session_date": day,
        "open_vnd": o,
        "high_vnd": h,
        "low_vnd": lo,
        "close_vnd": c,
        "volume": volume,
        "_source_id": source,
        "_batch_id": "fixture",
        "_ingested_at": at,
        "_payload_hash": "fixture",
        "_source_file": f"{source}.parquet",
        "_ingest_partition": at[:10],
    }


def series(symbol: str, k: int, first: int, last: int) -> list[dict]:
    """Deterministic prices on the symbol's tick; every third (or tenth) row stale."""
    base, tick = base_and_tick(symbol)
    rows, previous = [], None
    for i in range(first, last + 1):
        day = SESSIONS[i - 1]
        stale = previous is not None and (
            (symbol in STALE_EVERY_THIRD and (i + k) % 3 == 0) or (symbol == "S01" and i % 10 == 0)
        )
        if stale:
            rows.append(row(symbol, day, previous, previous, previous, previous, 0))
            continue
        close = base + tick * (((i * 7 + k * 13) % 21) - 10)
        open_ = close - tick * (((i + k) % 3) - 1)
        volume = 1_000_000 if symbol in LIQUID else 10_000 + (i % 5) * 1_000
        rows.append(
            row(
                symbol,
                day,
                open_,
                max(open_, close) + tick,
                min(open_, close) - tick,
                close,
                volume,
            )
        )
        previous = close
    return rows


def as_fallback(r: dict, **changes) -> dict:
    return {**r, "_source_id": FALLBACK, "_source_file": f"{FALLBACK}.parquet", **changes}


def at_session(rows: list[dict], symbol: str, i: int) -> dict:
    return next(r for r in rows if r["symbol"] == symbol and r["session_date"] == SESSIONS[i - 1])


def fixture() -> tuple[list[dict], list[dict]]:
    """(ohlcv rows, symbol-list rows) with the quirks each test must survive."""
    rows: list[dict] = []
    for k, symbol in enumerate(HOSE + HNX, start=1):
        rows += series(symbol, k, 1, len(SESSIONS))
    for k, symbol in enumerate(LATE, start=41):
        rows += series(symbol, k, 10, len(SESSIONS))
    rows += series(DELISTED_IN_LIST, 51, 1, 35) + series(NOT_IN_LIST, 52, 1, 35)

    # Rows every model must drop (primary only, no fallback): one per bad-row rule.
    at_session(rows, "S05", 20).update(open_vnd=0, high_vnd=0, low_vnd=0, close_vnd=0)
    at_session(rows, "S06", 21).update(close_vnd=None)
    bad = at_session(rows, "S07", 22)
    bad.update(close_vnd=bad["high_vnd"] + 50)
    bad = at_session(rows, "S08", 23)
    bad.update(open_vnd=bad["high_vnd"] + 50)

    # Fallback source: missing primary (S03), both clean (S10), broken primary (S04).
    # The fallback has 1-VND resolution (data-sources.md §5): off the 10-VND grid by design.
    for i in (30, 31, 32):
        r = at_session(rows, "S03", i)
        r.update(
            as_fallback(
                r, **{c: r[c] + 7 for c in ("open_vnd", "high_vnd", "low_vnd", "close_vnd")}
            )
        )
    for i in range(20, 25):
        r = at_session(rows, "S10", i)
        rows.append(as_fallback(r, close_vnd=r["close_vnd"] + 50, high_vnd=r["high_vnd"] + 50))
    r = at_session(rows, "S04", 40)
    rows.append(as_fallback(r))
    r.update(close_vnd=r["high_vnd"] + 50)

    # An older pull of one key: latest-wins must keep the newer one.
    r = at_session(rows, "S09", 25)
    rows.append(
        {
            **r,
            "close_vnd": r["close_vnd"] + 50,
            "high_vnd": r["high_vnd"] + 50,
            "_ingested_at": OLDER_PULL_AT,
            "_ingest_partition": OLDER_PULL_AT[:10],
        }
    )

    # Days that are not sessions: the known bad date, a Saturday pull, a partial pull after
    # the last session (v1's sparse tail).
    rows += [
        row(f"S{k:02d}", BAD_DATE, 20_000, 20_050, 19_950, 20_000, 1_000) for k in range(1, 36)
    ]
    rows += [row(f"S{k:02d}", SATURDAY, 20_000, 20_050, 19_950, 20_000, 100) for k in range(1, 6)]
    rows += [
        row(f"S{k:02d}", PARTIAL_DAY, 20_000, 20_050, 19_950, 20_000, 100) for k in range(1, 6)
    ]

    listed = [(s, "HSX") for s in HOSE + LATE] + [(s, "HNX") for s in HNX]
    symbols = [
        {
            "symbol": s,
            "exchange": e,
            "type": "stock",
            "_source_sha256": "fixture",
            "_loaded_at": PULLED_AT,
        }
        for s, e in [*listed, (DELISTED_IN_LIST, "DELISTED")]
    ]
    return rows, symbols


OLDER_SNAPSHOT_AT = "2026-04-01 09:00:00+00"


def flow_row(prefix: str, symbol: str, day: dt.date, value: float, at: str) -> dict:
    row_ = {"symbol": symbol, "session_date": day, "breakdown_valid": True, "source": "fixture"}
    for side in ("buy", "sell", "net"):
        for unit in ("vol", "val"):
            for src in ("matched", "deal", "total"):
                row_[f"{prefix}_{side}_{unit}_{src}"] = value
    return {**row_, "_source_sha256": f"sha-{at}", "_loaded_at": at}


def snapshot_tables() -> dict[str, Rows]:
    """Flow and index snapshots: an older and a newer one, so staging must pick the newest."""
    days = SESSIONS[:5]
    tables: dict[str, Rows] = {}
    for prefix, table in (("fr", "foreign_trade_daily"), ("prop", "prop_trade_daily")):
        tables[table] = [
            flow_row(prefix, s, d, 1_000_000.0 * (i + 1), at)
            for at in (OLDER_SNAPSHOT_AT, PULLED_AT)
            for i, s in enumerate(sorted(LIQUID))
            for d in days
        ]
    tables["index_daily"] = [
        {
            "index_code": code,
            "session_date": d,
            "open": 1300.0,
            "high": 1310.5,
            "low": 1295.25,
            "close": 1305.75,
            "volume": 1_000_000,
            "_source_id": PRIMARY,
            "_source_sha256": f"sha-{at}",
            "_loaded_at": at,
        }
        for at in (OLDER_SNAPSHOT_AT, PULLED_AT)
        for code in ("VNINDEX", "VN30")
        for d in SESSIONS
    ]
    return tables


# --- faults ---------------------------------------------------------------------------

Rows = list[dict]


@dataclasses.dataclass(frozen=True)
class Mutant:
    """One model's SQL changed: `old` must occur exactly `occurrences` times."""

    file: str
    old: str
    new: str
    occurrences: int = 1


SeedEdit = Callable[[list[dict]], list[dict]]


@dataclasses.dataclass(frozen=True)
class Fault:
    name: str
    mechanism: str
    expected: dict[str, str]  # test name -> status (fail or warn)
    data: Callable[[Rows], Rows] | None = None  # change the raw rows before the build
    mutants: tuple[Mutant, ...] = ()
    seed_edits: tuple[tuple[str, SeedEdit], ...] = ()  # (seed name, rows -> rows)
    vars: dict | None = None
    after_build: Callable[[], Rows] | None = None  # raw rows loaded after the build
    snapshots: Callable[[dict[str, Rows]], dict[str, Rows]] | None = None  # change snapshots


def warn(*names: str) -> dict[str, str]:
    return dict.fromkeys(names, "warn")


def set_column(column: str, value: str, where: Callable[[dict], bool] = lambda r: True) -> SeedEdit:
    return lambda rows: [{**r, column: value} if where(r) else r for r in rows]


def duplicate(where: Callable[[dict], bool]) -> SeedEdit:
    return lambda rows: rows + [dict(r) for r in rows if where(r)]


def fail(*names: str) -> dict[str, str]:
    return dict.fromkeys(names, "fail")


def drop_rows(predicate: Callable[[dict], bool]) -> Callable[[Rows], Rows]:
    return lambda rows: [r for r in rows if not predicate(r)]


def edit_rows(predicate: Callable[[dict], bool], **changes) -> Callable[[Rows], Rows]:
    return lambda rows: [{**r, **changes} if predicate(r) else r for r in rows]


def to_fallback(symbol: str, sessions: range) -> Callable[[Rows], Rows]:
    days = {SESSIONS[i - 1] for i in sessions}
    return lambda rows: [
        as_fallback(r) if r["symbol"] == symbol and r["session_date"] in days else r for r in rows
    ]


def full_pull(day: dt.date) -> Rows:
    return [row(s, day, 20_000, 20_050, 19_950, 20_000, 1_000) for s in HOSE + HNX]


def add_rows(extra: Callable[[], Rows]) -> Callable[[Rows], Rows]:
    return lambda rows: rows + extra()


FCT = "models/marts/daily/fct_price_daily.sql"
LIQ = "models/marts/daily/fct_liquidity_daily.sql"
UNI = "models/marts/daily/fct_universe_daily.sql"
CAL = "models/marts/daily/dim_trading_calendar.sql"
SEC = "models/marts/daily/dim_security.sql"
CHOSEN = "models/intermediate/int_prices__chosen_source.sql"
STG = "models/staging/stg_vnstock__ohlcv_daily.sql"
GRAIN = {
    "fct": "unique_combination_fct_price_daily_symbol__trade_date",
    "liq": "unique_combination_fct_liquidity_daily_symbol__trade_date",
    "uni": "unique_combination_fct_universe_daily_symbol__trade_date",
}
NOT_EMPTY = [
    "not_empty_stg_vnstock__ohlcv_daily_",
    "not_empty_dim_security_",
    "not_empty_fct_price_daily_",
    "not_empty_fct_liquidity_daily_",
    "not_empty_fct_universe_daily_",
]
# as_of tests as _seeds.yml declares them (seed name, days), named as dbt names them.
AS_OF = {
    seed[
        "name"
    ]: f"as_of_within_days_{seed['name']}_{test['as_of_within_days']['arguments']['days']}"
    for seed in SEED_TESTS
    for test in seed.get("data_tests", [])
    if isinstance(test, dict) and "as_of_within_days" in test
}

FAULTS = [
    Fault(
        "empty_raw",
        "a load that wrote nothing (echoes: every model below raw is empty too)",
        {
            **fail(*NOT_EMPTY, "assert_last_session_has_enough_symbols"),
            **warn(
                "assert_universe_covers_falling_markets",
                "assert_watched_symbols_have_every_session",
            ),
        },
        data=lambda rows: [],
    ),
    Fault(
        "empty_flow_and_index_snapshots",
        "flow and index loads that wrote nothing",
        fail(
            "not_empty_stg_vnstock__foreign_trade_",
            "not_empty_stg_vnstock__prop_trade_",
            "not_empty_stg_vnstock__index_daily_",
        ),
        snapshots=lambda tables: dict.fromkeys(tables, []),
    ),
    Fault(
        "older_snapshots_kept",
        "the newest-snapshot filter lost in staging",
        fail(
            "unique_combination_stg_vnstock__foreign_trade_symbol__trade_date",
            "unique_combination_stg_vnstock__prop_trade_symbol__trade_date",
            "unique_combination_stg_vnstock__index_daily_index_code__trade_date",
        ),
        mutants=tuple(
            Mutant(
                f"models/staging/stg_vnstock__{name}.sql",
                "where _loaded_at = (",
                "where _loaded_at <= (",
            )
            for name in ("foreign_trade", "prop_trade", "index_daily")
        ),
    ),
    Fault(
        "stale_rule_seeds",
        "rule seeds not reviewed for a quarter",
        fail(*AS_OF.values()),
        seed_edits=tuple((s, set_column("as_of", "2000-01-03")) for s in AS_OF),
    ),
    Fault(
        "duplicate_tick_row",
        "a tick row added twice",
        fail(
            "unique_combination_tick_size_exchange__instrument_class__price_from_vnd__effective_from"
        ),
        seed_edits=(
            (
                "tick_size",
                duplicate(lambda r: r["exchange"] == "HNX" and r["instrument_class"] == "stock"),
            ),
        ),
    ),
    Fault(
        "duplicate_band_row",
        "a band row added twice (echoes: the band join doubles the "
        "HNX price rows, so a symbol's first row gains a 'previous' row for ADV)",
        fail(
            "unique_combination_price_band_exchange__band_case__effective_from",
            GRAIN["fct"],
            GRAIN["liq"],
            GRAIN["uni"],
            "assert_adv_excludes_current_row",
        ),
        seed_edits=(
            (
                "price_band",
                duplicate(lambda r: r["exchange"] == "HNX" and r["band_case"] == "normal"),
            ),
        ),
    ),
    Fault(
        "duplicate_exchange_change",
        "an announced move entered twice (echo: every HNX symbol's periods doubled)",
        fail(
            "unique_combination_exchange_changes_from_exchange__effective_from",
            "unique_combination_dim_security_symbol__effective_from",
        ),
        seed_edits=(("exchange_changes", duplicate(lambda r: r["from_exchange"] == "HNX")),),
    ),
    Fault(
        "next_year_holidays_missing",
        "December without next year's holidays",
        fail("assert_next_year_holidays_seeded"),
        vars={"dq_holiday_check_date": "2027-12-05"},
    ),
    Fault(
        "older_pull_kept",
        "latest-wins filter lost in staging",
        fail("unique_combination_stg_vnstock__ohlcv_daily__source_id__symbol__trade_date"),
        mutants=(Mutant(STG, "where pull_rank = 1", "where pull_rank >= 1", 1),),
    ),
    # Defects dbt carries downstream: the echoes are named, each one explained.
    Fault(
        "both_sources_kept",
        "source choice keeps every source's row (echoes: the flagged "
        "grain and the fallback rows let through; fct_price_daily's tick rank keeps one row "
        "per key, so the marts' grains stay green)",
        fail(
            "unique_combination_int_prices__chosen_source_symbol__trade_date",
            "unique_combination_int_prices__flagged_symbol__trade_date",
            "assert_fallback_only_without_clean_primary",
        ),
        mutants=(Mutant(CHOSEN, "where source_rank = 1", "where source_rank >= 1"),),
    ),
    Fault(
        "delisted_split_by_move",
        "the move splits delisted symbols too (the price rows "
        "joining both periods are cut back to one by the tick rank)",
        fail("unique_combination_dim_security_symbol__effective_from"),
        mutants=(
            Mutant(
                SEC,
                "join moves as m on m.from_exchange = c.exchange and not c.is_delisted",
                "join moves as m on m.from_exchange = c.exchange",
                2,
            ),
        ),
    ),
    Fault(
        "full_pull_on_a_saturday",
        "a source dates a full session on a Saturday",
        fail("assert_no_session_on_weekend"),
        data=add_rows(lambda: full_pull(SATURDAY + dt.timedelta(days=7))),
    ),
    Fault(
        "nonpositive_close_kept",
        "the non-positive drop rule lost",
        fail("price_close_positive"),
        mutants=(Mutant(FCT, "and not p.is_bad_nonpositive", "", 1),),
    ),
    Fault(
        "null_close_kept",
        "the null drop rule lost",
        fail("not_null_fct_price_daily_close_vnd"),
        # A null close makes the non-positive and OHLC flags null too, and each drops the
        # row on its own; the regression is a rewrite that reads unknown as clean.
        mutants=(
            Mutant(FCT, "where not p.is_bad_null", "where true", 1),
            Mutant(
                FCT,
                "and not p.is_bad_nonpositive",
                "and coalesce(not p.is_bad_nonpositive, true)",
                1,
            ),
            Mutant(FCT, "and not p.is_bad_ohlc", "and coalesce(not p.is_bad_ohlc, true)", 1),
        ),
    ),
    Fault(
        "close_outside_range_kept",
        "the OHLC drop rule lost",
        fail("price_close_within_low_high"),
        mutants=(Mutant(FCT, "and not p.is_bad_ohlc", "", 1),),
    ),
    Fault(
        "open_outside_range_kept",
        "v1's open drop rule lost",
        fail("price_open_within_low_high"),
        mutants=(Mutant(FCT, "and not (p.is_stale = false and p.is_open_outside_range)", "", 1),),
    ),
    Fault(
        "negative_volume",
        "a source row with negative volume",
        fail("price_volume_not_negative"),
        data=edit_rows(
            lambda r: r["symbol"] == "S13" and r["session_date"] == SESSIONS[33], volume=-100
        ),
    ),
    Fault(
        "price_in_thousands",
        "one row in thousands of VND (19.45 read as 19)",
        fail("price_close_multiple_of_10_vnd"),
        data=edit_rows(
            lambda r: r["symbol"] == "S12" and r["session_date"] == SESSIONS[32],
            open_vnd=19,
            high_vnd=19,
            low_vnd=19,
            close_vnd=19,
        ),
    ),
    Fault(
        "non_session_rows_kept",
        "the calendar joined without is_trading_day",
        fail("assert_price_dates_are_trading_days"),
        mutants=(
            Mutant(
                FCT,
                "on c.calendar_date = p.trade_date and c.is_trading_day",
                "on c.calendar_date = p.trade_date",
                1,
            ),
        ),
    ),
    Fault(
        "session_seq_per_symbol",
        "session_seq counted per symbol",
        fail("assert_price_session_seq_matches_calendar"),
        mutants=(
            Mutant(
                FCT,
                "p.is_stale, p._source_id, c.session_seq, c.trading_week_id",
                "p.is_stale, p._source_id, row_number() over (partition by p.symbol order by "
                "p.trade_date) as session_seq, c.trading_week_id",
                1,
            ),
        ),
    ),
    Fault(
        "adv_window_too_wide",
        "ADV window one row wider than configured",
        fail("assert_adv_rows_within_window"),
        mutants=(
            Mutant(
                LIQ,
                "rows between {{ var('adv_window_rows') }} preceding and 1 preceding",
                "rows between {{ var('adv_window_rows') + 1 }} preceding and 1 preceding",
                1,
            ),
        ),
    ),
    Fault(
        "adv_reads_current_row",
        "ADV window shifted onto the current row",
        fail("assert_adv_excludes_current_row"),
        mutants=(
            Mutant(
                LIQ,
                "rows between {{ var('adv_window_rows') }} preceding and 1 preceding",
                "rows between {{ var('adv_window_rows') - 1 }} preceding and current row",
                1,
            ),
        ),
    ),
    Fault(
        "stale_rows_in_universe",
        "both stale guards lost",
        fail("assert_no_stale_row_in_universe"),
        mutants=(
            Mutant(LIQ, "where is_stale = false", "where true", 1),
            Mutant(UNI, "    and p.is_stale = false\n", "", 1),
        ),
    ),
    Fault(
        "watched_symbol_month_missing",
        "a source cut a month of a liquid symbol",
        warn("assert_watched_symbols_have_every_session"),
        data=drop_rows(
            lambda r: r["symbol"] == "S02" and r["session_date"] in set(SESSIONS[29:49])
        ),
    ),
    Fault(
        "raw_loaded_without_rebuild",
        "raw advanced, dbt not rerun (v1 2026-08-03)",
        fail("assert_marts_not_behind_raw"),
        after_build=lambda: full_pull(PARTIAL_DAY + dt.timedelta(days=1)),
    ),
    Fault(
        "partial_tail_kept",
        "the cut after the last observed session lost",
        fail("assert_last_session_has_enough_symbols"),
        mutants=(Mutant(FCT, "and p.trade_date <= lo.last_session", "", 1),),
    ),
    Fault(
        "current_exchange_for_every_date",
        "the security join ignores effective dates",
        fail("assert_price_exchange_matches_security_period"),
        mutants=(
            Mutant(
                FCT,
                "and (s.effective_from is null or k.trade_date >= s.effective_from)\n"
                "        and (s.effective_to is null or k.trade_date < s.effective_to)",
                "and s.effective_to is null",
                1,
            ),
        ),
    ),
    Fault(
        "inferred_exchange_preferred",
        "tick inference preferred over the list",
        fail("assert_listed_exchange_from_symbol_list"),
        mutants=(
            Mutant(
                SEC,
                "coalesce(l.exchange, i.inferred_exchange) as exchange",
                "coalesce(i.inferred_exchange, l.exchange) as exchange",
                1,
            ),
        ),
    ),
    Fault(
        "fallback_preferred",
        "the fallback wins over a clean primary row",
        fail("assert_fallback_only_without_clean_primary"),
        mutants=(
            Mutant(
                CHOSEN,
                """case when _source_id = '{{ var("primary_price_source") }}' then 0 else 1 end""",
                """case when _source_id = '{{ var("primary_price_source") }}' then 1 else 0 end""",
                1,
            ),
        ),
    ),
    Fault(
        "primary_stopped_for_a_traded_symbol",
        "a source stopped; the fallback carries a liquid symbol",
        {"monitor_fallback_rows_in_universe_symbols": "warn"},
        data=to_fallback("S02", range(50, 60)),
    ),
    Fault(
        "calendar_numbers_every_day",
        "session_seq counted over calendar days",
        fail("assert_calendar_session_seq_has_no_gap"),
        mutants=(
            Mutant(
                CAL,
                "sum(case when is_trading_day then 1 else 0 end)\n            over (order by "
                "calendar_date rows between unbounded preceding and current row)",
                "row_number() over (order by calendar_date)",
                1,
            ),
        ),
    ),
    Fault(
        "holidays_ignored_by_rule",
        "the weekday rule without the holiday seed (v1 2027)",
        fail("assert_no_session_on_seeded_holiday"),
        mutants=(
            Mutant(
                CAL,
                "else {{ is_weekday('s.calendar_date') }} and h.holiday_date is null",
                "else {{ is_weekday('s.calendar_date') }}",
                1,
            ),
        ),
    ),
    Fault(
        "calendar_range_inverted",
        "calendar first and last dates swapped in config "
        "(echoes: no session, so no price row and nothing below it)",
        fail(
            "not_empty_dim_trading_calendar_",
            "not_empty_fct_price_daily_",
            "not_empty_fct_liquidity_daily_",
            "not_empty_fct_universe_daily_",
            "assert_last_session_has_enough_symbols",
        )
        | warn("assert_universe_covers_falling_markets"),
        vars={"calendar_first_date": "2027-12-31", "calendar_last_date": "2005-01-01"},
    ),
    Fault(
        "tier_thresholds_in_wrong_unit",
        "liquidity tiers entered in VND x 1,000",
        warn("assert_universe_covers_falling_markets"),
        vars={
            "liquidity_tier_high_vnd": 10**14,
            "liquidity_tier_medium_vnd": 3 * 10**13,
            "liquidity_tier_low_vnd": 10**13,
        },
    ),
]


# --- comparison (pure, self-tested) --------------------------------------------------


def red_tests(run_results: dict, names: dict[str, str]) -> dict[str, str]:
    """{test name: status} for every test that did not pass; `names` maps unique_id -> name."""
    return {
        names.get(r["unique_id"], r["unique_id"]): r["status"]
        for r in run_results["results"]
        if r["unique_id"].startswith("test.") and r["status"] in RED
    }


def problems_for(fault: Fault, red: dict[str, str]) -> list[str]:
    out = []
    for name in sorted(set(fault.expected) | set(red)):
        want, got = fault.expected.get(name), red.get(name)
        if want != got:
            out.append(f"{name}: expected {want or 'pass'}, got {got or 'pass'}")
    return out


def uncovered(data_tests: dict[str, str], faults: list[Fault]) -> list[str]:
    """Data tests (name -> kind) never red in any fault; built-ins are exempt."""
    covered = {name for f in faults for name in f.expected}
    return sorted(
        n for n, kind in data_tests.items() if kind not in BUILTIN_TESTS and n not in covered
    )


def data_tests_of(manifest: dict) -> dict[str, str]:
    """{name: kind} of every data test (not unit tests); kind is the generic test's name."""
    return {
        node["name"]: (node.get("test_metadata") or {}).get("name", "singular")
        for node in manifest["nodes"].values()
        if node["resource_type"] == "test"
    }


# --- running dbt -----------------------------------------------------------------------


class CannotRun(Exception):
    pass


def dbt_executable() -> str:
    found = shutil.which("dbt", path=str(Path(sys.executable).parent)) or shutil.which("dbt")
    if not found:
        raise CannotRun("dbt is not installed (pip install -e '.[dbt]')")
    return found


STEP_SECONDS: list[float] = []  # every dbt step's duration, reported at the end


def dbt_argv(project: Path, args: tuple[str, ...], vars_: dict | None) -> list[str]:
    argv = [
        dbt_executable(),
        *args,
        "--no-partial-parse",
        "--target",
        "ci",
        "--project-dir",
        str(project),
        "--profiles-dir",
        str(project / "ci"),
    ]
    if vars_:
        argv += ["--vars", json.dumps(vars_)]
    return argv


def invoke(project: Path, args: tuple[str, ...], vars_: dict | None, allowed: tuple[int, ...]):
    started = time.monotonic()
    try:
        done = run_bounded(dbt_argv(project, args, vars_), STEP_TIMEOUT_SECONDS, cwd=project)
    except Timeout as exc:
        raise CannotRun(f"dbt {args[0]}: {exc}") from exc
    STEP_SECONDS.append(time.monotonic() - started)
    if done.returncode not in allowed:
        raise CannotRun(f"dbt {' '.join(args)} exited {done.returncode}:\n{done.stdout[-3000:]}")


def dbt_step(project: Path, *args: str, vars_: dict | None = None) -> None:
    """A dbt step that must succeed (seed, run, run-operation)."""
    invoke(project, args, vars_, allowed=(0,))


def dbt_test(project: Path, vars_: dict) -> dict:
    """Run the data tests; exit 1 (a red test) is expected for a fault. The previous
    run_results.json is removed first, so a crash cannot be read as the last run's result."""
    results = project / "target" / "run_results.json"
    results.unlink(missing_ok=True)
    invoke(project, ("test", "--exclude", "test_type:unit"), vars_, allowed=(0, 1))
    if not results.exists():
        raise CannotRun("dbt test wrote no run_results.json")
    run = json.loads(results.read_text("utf-8"))
    if skipped := skipped_tests(run):  # a skipped test would read as passed
        raise CannotRun(f"dbt skipped {len(skipped)} tests, e.g. {skipped[0]}")
    return run


def skipped_tests(run_results: dict) -> list[str]:
    return [r["unique_id"] for r in run_results["results"] if r["status"] == "skipped"]


def sql_value(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, int | float):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def load(db: Path, table: str, rows: Rows, *, replace: bool) -> None:
    import duckdb

    con = duckdb.connect(str(db))
    try:
        if replace:
            con.execute(f"delete from raw_vnstock.{table}")  # noqa: S608 - a literal table
        if rows:
            columns = list(rows[0])
            for start in range(0, len(rows), 500):
                values = ",\n".join(
                    "(" + ", ".join(sql_value(r[c]) for c in columns) + ")"
                    for r in rows[start : start + 500]
                )
                # The values come from this file's fixture, quoted by sql_value.
                insert = f"insert into raw_vnstock.{table} ({', '.join(columns)}) values "  # noqa: S608 - a literal table
                con.execute(insert + values)
    finally:
        con.close()


def copy_project(target: Path) -> Path:
    def skipped(directory: str, names: list[str]) -> set[str]:
        # The owner's profiles.yml (git-ignored) stays behind; ci/profiles.yml is used.
        top = Path(directory) == DBT_DIR
        return {
            n
            for n in names
            if n in {"target", "logs", "dbt_packages", ".user.yml"} or (top and n == "profiles.yml")
        }

    shutil.copytree(DBT_DIR, target, ignore=skipped)
    edit_seed(
        target,
        "exchange_changes",
        set_column("effective_from", MOVE_DATE, lambda r: r["from_exchange"] == "HNX"),
    )
    return target


def mutate(project: Path, m: Mutant) -> None:
    """Apply a mutant; one that no longer applies stops the run instead of passing silently."""
    path = project / m.file
    text = path.read_text("utf-8")
    if text.count(m.old) != m.occurrences:
        raise CannotRun(
            f"{m.file}: expected {m.occurrences} x {m.old[:60]!r}, found {text.count(m.old)}"
        )
    path.write_text(text.replace(m.old, m.new), "utf-8", newline="\n")


def edit_seed(project: Path, seed: str, change: SeedEdit) -> None:
    """Rewrite a seed CSV through `change`; an edit that changes nothing stops the run."""
    path = project / "seeds" / f"{seed}.csv"
    rows = list(csv.DictReader(io.StringIO(path.read_text("utf-8"))))
    changed = change(rows)
    if changed == rows:
        raise CannotRun(f"seed edit on {seed} changed nothing")
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(changed)
    path.write_text(out.getvalue(), "utf-8", newline="\n")


def run_matrix(only: set[str], keep: Path | None) -> int:
    work = Path(tempfile.mkdtemp(prefix="planted_faults_")) if keep is None else keep
    try:
        control = copy_project(work / "control")
        db = control / "target" / "ci.duckdb"
        db.parent.mkdir(parents=True, exist_ok=True)
        dbt_step(control, "run-operation", "create_ci_sources")
        rows, symbols = fixture()
        load(db, "ohlcv_daily", rows, replace=True)
        load(db, "ref_symbols_by_exchange", symbols, replace=True)
        for table, table_rows in snapshot_tables().items():
            load(db, table, table_rows, replace=True)
        dbt_step(control, "seed", vars_=FIXTURE_VARS)
        dbt_step(control, "run", vars_=FIXTURE_VARS)
        results = dbt_test(control, FIXTURE_VARS)
        manifest = json.loads((control / "target" / "manifest.json").read_text("utf-8"))
        names = {uid: node["name"] for uid, node in manifest["nodes"].items()}
        tests = data_tests_of(manifest)
        failures: list[str] = []

        red = red_tests(results, names)
        print(
            f"{'✅' if not red else '🔴'} control: {len(tests)} data tests, "
            f"{len(rows)} fixture rows, red = {sorted(red) or 'none'}"
        )
        if red:
            failures.append("control")

        for fault in FAULTS:
            if only and fault.name not in only:
                continue
            project = shutil.copytree(control, work / fault.name)
            for m in fault.mutants:
                mutate(project, m)
            for seed, change in fault.seed_edits:
                edit_seed(project, seed, change)
            vars_ = {**FIXTURE_VARS, **(fault.vars or {})}
            fault_db = project / "target" / "ci.duckdb"
            if fault.data:
                load(fault_db, "ohlcv_daily", fault.data(fixture()[0]), replace=True)
            if fault.snapshots:
                for table, table_rows in fault.snapshots(snapshot_tables()).items():
                    load(fault_db, table, table_rows, replace=True)
            if fault.seed_edits:
                dbt_step(project, "seed", vars_=vars_)
            if fault.after_build:
                load(fault_db, "ohlcv_daily", fault.after_build(), replace=False)
            else:
                dbt_step(project, "run", vars_=vars_)
            res = dbt_test(project, vars_)
            problems = problems_for(fault, red_tests(res, names))
            print(f"{'✅' if not problems else '🔴'} {fault.name}: {fault.mechanism}")
            for p in problems:
                print(f"     {p}")
            if problems:
                failures.append(fault.name)
            if keep is None:
                shutil.rmtree(project, ignore_errors=True)

        if not only:
            missing = uncovered(tests, FAULTS)
            print(
                f"{'✅' if not missing else '🔴'} coverage: every non-built-in data test red "
                f"in some fault{'' if not missing else ' - never red: ' + ', '.join(missing)}"
            )
            if missing:
                failures.append("coverage")
            unknown = sorted({n for f in FAULTS for n in f.expected} - set(tests))
            if unknown:
                print(f"🔴 faults name tests that do not exist: {', '.join(unknown)}")
                failures.append("unknown tests")
        print(
            f"   {len(STEP_SECONDS)} dbt steps, slowest {max(STEP_SECONDS):.1f}s "
            f"(limit {STEP_TIMEOUT_SECONDS}s, config/dq.yml)"
        )
        return 1 if failures else 0
    finally:
        if keep is None:
            shutil.rmtree(work, ignore_errors=True)


# --- self-test -----------------------------------------------------------------------


def raises_cannot_run(action: Callable[[], object]) -> bool:
    try:
        action()
    except CannotRun:
        return True
    return False


def seed_edit_rejected() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "seeds").mkdir()
        (Path(tmp) / "seeds" / "s.csv").write_text("a,b\n1,2\n", "utf-8")
        return raises_cannot_run(lambda: edit_seed(Path(tmp), "s", lambda rows: rows))


def self_test() -> int:
    """The comparison, coverage and fixture invariants, offline and without dbt."""
    rr = {
        "results": [
            {"unique_id": "test.p.a.1", "status": "fail"},
            {"unique_id": "test.p.b.2", "status": "pass"},
            {"unique_id": "test.p.c.3", "status": "warn"},
            {"unique_id": "model.p.m", "status": "success"},
        ]
    }
    names = {"test.p.a.1": "a", "test.p.b.2": "b", "test.p.c.3": "c"}
    exact = Fault("x", "m", {"a": "fail", "c": "warn"})
    target_missed = Fault("x", "m", {"b": "fail"})
    rows, symbols = fixture()
    traded = {}
    for r in rows:
        if r["_source_id"] == PRIMARY and (r["volume"] or 0) > 0:
            traded.setdefault(r["session_date"], set()).add(r["symbol"])
    checks = {
        "red tests read from statuses, models ignored": red_tests(rr, names)
        == {"a": "fail", "c": "warn"},
        "control: the exact expected set has no problem": problems_for(exact, red_tests(rr, names))
        == [],
        "planted: a missed target and an unexpected red are both reported": len(
            problems_for(target_missed, red_tests(rr, names))
        )
        == 3,
        "planted: warn where fail was expected is a mismatch": problems_for(
            Fault("x", "m", {"a": "fail", "c": "fail"}), red_tests(rr, names)
        )
        != [],
        "coverage: built-ins exempt, an uncovered custom test reported": uncovered(
            {"a": "singular", "u": "unique", "z": "row_condition"}, [exact]
        )
        == ["z"],
        "fixture: every session has enough traded symbols on the primary": all(
            len(traded.get(d, ())) >= MIN_TRADED for d in SESSIONS
        ),
        "fixture: the Saturday and the partial day stay below that": all(
            len(traded.get(d, ())) < MIN_TRADED for d in (SATURDAY, PARTIAL_DAY)
        ),
        "planted: a mutant that no longer applies stops the run": raises_cannot_run(
            lambda: mutate(REPO_ROOT, Mutant("dbt/dbt_project.yml", "no such text", "x"))
        ),
        "planted: a seed edit that changes nothing stops the run": seed_edit_rejected(),
        "planted: a skipped test is detected (it would read as passed)": skipped_tests(
            {"results": [{"unique_id": "test.p.s", "status": "skipped"}]}
        )
        == ["test.p.s"],
        "faults: every as_of seed test is known": len(AS_OF) >= 5,
        "fixture: deterministic": fixture() == (rows, symbols)
        and snapshot_tables() == snapshot_tables(),
        "fixture: every snapshot table has an older and a newer snapshot": all(
            {r["_loaded_at"] for r in v} == {OLDER_SNAPSHOT_AT, PULLED_AT}
            for v in snapshot_tables().values()
        ),
        "fixture: every regular price is on its tick": all(
            r["close_vnd"] % base_and_tick(r["symbol"])[1] == 0
            for r in rows
            if r["session_date"] in SESSIONS
            and r["close_vnd"]
            and r["_source_id"] == PRIMARY
            and r["symbol"] not in {"S07", "S04"}
        ),
        "faults: names unique": len({f.name for f in FAULTS}) == len(FAULTS),
        "faults: every fault expects at least one red test": all(f.expected for f in FAULTS),
        "an unknown argument is rejected with exit 2": run_bounded(
            [sys.executable, __file__, "--bogus"], 120
        ).returncode
        == 2,
    }
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    parser.add_argument(
        "--fault",
        action="append",
        default=[],
        choices=[f.name for f in FAULTS],
        help="run only this fault (repeatable); coverage is then not judged",
    )
    parser.add_argument("--list", action="store_true", help="list the faults and exit")
    parser.add_argument("--keep", type=Path, help="keep the work directories here (debugging)")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    if args.self_test:
        return self_test()
    if args.list:
        for f in FAULTS:
            print(f"{f.name}: {f.mechanism} -> {', '.join(f.expected)}")
        return 0
    try:
        return run_matrix(set(args.fault), args.keep)
    except CannotRun as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
