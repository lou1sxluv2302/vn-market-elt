"""Build a larger synthetic warehouse for the README's dashboard pictures (no market data).

The planted-fault fixture (`planted_faults.py`) is small on purpose: every row is there to
make one test fail. Its dashboard looks empty. This generates a market that looks like one -
200 symbols on HOSE and HNX over two years, eight supersectors, a market factor that rises,
corrects and recovers, stale sessions on illiquid symbols, listings and delistings, foreign
and proprietary flows, three indices - then builds the dbt project on DuckDB from it, as the
fault harness does. Symbols are named S001-S200 so nothing can be read as a real company.

Every generated price respects the rules the warehouse checks: the exchange's tick size for
its price, the daily band against the previous close, low <= open, close <= high; a stale
session has volume 0 and copies the previous close. `problems()` checks this before anything
is loaded, so a generator bug stops the build instead of reaching a picture.

Exit codes: 0 = dry run listed, or built with `--apply` · 1 = generated rows broke a rule,
or a self-test failed · 2 = cannot run (dbt missing, a dbt step failed, an unknown argument).

Usage:
    python tools/demo_warehouse.py --out <DIR>            # dry run: what would be built
    python tools/demo_warehouse.py --out <DIR> --apply    # writes <DIR>/target/ci.duckdb
    python tools/demo_warehouse.py --self-test
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import math
import random
import sys
from pathlib import Path

from planted_faults import CannotRun, copy_project, dbt_step, load, row

from vnmarket.common.config import utf8_stdio

SEED = 20261127
FIRST, LAST = dt.date(2024, 1, 2), dt.date(2025, 12, 31)
HOLIDAYS = (
    {dt.date(2024, 1, 1), dt.date(2025, 1, 1)}
    | {dt.date(2024, 2, 8) + dt.timedelta(days=i) for i in range(7)}  # Tet 2024
    | {dt.date(2025, 1, 27) + dt.timedelta(days=i) for i in range(5)}  # Tet 2025
    | {dt.date(2024, 4, 30), dt.date(2024, 5, 1), dt.date(2025, 4, 30), dt.date(2025, 5, 1)}
    | {dt.date(2024, 9, 2), dt.date(2024, 9, 3), dt.date(2025, 9, 1), dt.date(2025, 9, 2)}
)
LOADED_AT = "2026-01-02 09:00:00+00"
BAND = {"HOSE": 0.07, "HNX": 0.10}  # the price_band seed, normal case
BAND_MARGIN = 0.005  # stay this far inside the band, so tick rounding never crosses it
# The market factor: (sessions, mean daily return, daily volatility), one regime after another.
REGIMES = [
    (110, 0.0012, 0.008),  # rise
    (55, -0.0028, 0.013),  # correction
    (95, 0.0002, 0.007),  # sideways
    (130, 0.0015, 0.009),  # rise
    (35, -0.0040, 0.016),  # sharp fall
    (1000, 0.0010, 0.009),  # recovery to the end
]
# ICB: (level-1 code, Vietnamese, English), (level-2 code, Vietnamese, English), symbols
SECTORS = [
    (("8000", "Tài chính", "Financials"), ("8300", "Ngân hàng", "Banks"), 28),
    (("8000", "Tài chính", "Financials"), ("8700", "Dịch vụ tài chính", "Financial Services"), 22),
    (("8000", "Tài chính", "Financials"), ("8600", "Bất động sản", "Real Estate"), 32),
    (
        ("1000", "Nguyên vật liệu", "Basic Materials"),
        ("1700", "Tài nguyên cơ bản", "Basic Resources"),
        24,
    ),
    (
        ("2000", "Công nghiệp", "Industrials"),
        ("2300", "Xây dựng và vật liệu", "Construction & Materials"),
        30,
    ),
    (
        ("3000", "Hàng tiêu dùng", "Consumer Goods"),
        ("3500", "Thực phẩm và đồ uống", "Food & Beverage"),
        24,
    ),
    (("9000", "Công nghệ", "Technology"), ("9500", "Công nghệ thông tin", "Technology"), 14),
    (("0001", "Dầu khí", "Oil & Gas"), ("0500", "Dầu khí", "Oil & Gas"), 26),
]
N_HNX = 60
N_LATE, N_DELISTED = 8, 3
STALE_SHARE, STALE_DAY_CHANCE = 0.15, 0.35
FLOW_MIN_TURNOVER_VND = 20e9  # symbols with flows: median turnover above this


@dataclasses.dataclass(frozen=True)
class Symbol:
    code: str
    exchange: str  # HOSE or HNX
    sector: int  # index into SECTORS
    beta: float
    start_price: int
    turnover_vnd: float  # median daily turnover
    illiquid: bool
    first: int  # first session index
    last: int  # last session index (inclusive)


def sessions(first: dt.date = FIRST, last: dt.date = LAST) -> list[dt.date]:
    days = (first + dt.timedelta(days=i) for i in range((last - first).days + 1))
    return [d for d in days if d.weekday() < 5 and d not in HOLIDAYS]


def tick(exchange: str, price: float) -> int:
    """The tick_size seed: HOSE 10 below 10,000, 50 below 50,000, else 100; HNX 100."""
    if exchange == "HNX":
        return 100
    return 10 if price < 10_000 else 50 if price < 50_000 else 100


def on_tick(exchange: str, price: float, inward_from: float) -> int:
    """Round to the tick, towards `inward_from` (the previous close), so a price at the band's
    edge never rounds outside it."""
    t = tick(exchange, price)
    return int((math.floor if price > inward_from else math.ceil)(price / t) * t)


def market_factor(n: int, rng: random.Random) -> list[float]:
    out: list[float] = []
    for length, mean, vol in REGIMES:
        out += [rng.gauss(mean, vol) for _ in range(length)]
    return out[:n]


def universe(n_sessions: int, rng: random.Random) -> list[Symbol]:
    codes = iter(f"S{k:03d}" for k in range(1, 1000))
    symbols: list[Symbol] = []
    for s, (_, _, count) in enumerate(SECTORS):
        for _ in range(count):
            symbols.append(
                Symbol(
                    code=next(codes),
                    exchange="HOSE",
                    sector=s,
                    beta=rng.uniform(0.6, 1.4),
                    start_price=int(rng.uniform(8_000, 90_000)),
                    turnover_vnd=math.exp(rng.gauss(math.log(14e9), 1.1)),
                    illiquid=False,
                    first=0,
                    last=n_sessions - 1,
                )
            )
    rng.shuffle(symbols)
    out = []
    for k, sym in enumerate(symbols):
        late = k < N_LATE
        delisted = N_LATE <= k < N_LATE + N_DELISTED
        out.append(
            dataclasses.replace(
                sym,
                exchange="HNX" if k >= len(symbols) - N_HNX else "HOSE",
                illiquid=rng.random() < STALE_SHARE,
                first=rng.randrange(n_sessions // 8, n_sessions // 2) if late else 0,
                last=rng.randrange(n_sessions // 2, n_sessions - n_sessions // 12)
                if delisted
                else n_sessions - 1,
            )
        )
    return sorted(out, key=lambda s: s.code)


def generate(days: list[dt.date], seed: int = SEED):
    """(ohlcv rows, symbol-list rows, flow rows by table, index rows, symbols)."""
    rng = random.Random(seed)  # noqa: S311 - synthetic prices, not secrets
    n = len(days)
    market = market_factor(n, rng)
    sector_moves = [
        [rng.gauss(0.0002 * (s % 3 - 1), 0.006) for _ in range(n)] for s in range(len(SECTORS))
    ]
    symbols = universe(n, rng)
    rows, flows = [], {"foreign_trade_daily": [], "prop_trade_daily": []}
    for sym in symbols:
        band = BAND[sym.exchange] - BAND_MARGIN
        close = float(on_tick(sym.exchange, sym.start_price, 0))
        for i in range(sym.first, sym.last + 1):
            day = days[i]
            if sym.illiquid and i > sym.first and rng.random() < STALE_DAY_CHANCE:
                c = int(close)
                rows.append(row(sym.code, day, c, c, c, c, 0))
                continue
            r = sym.beta * market[i] + sector_moves[sym.sector][i] + rng.gauss(0, 0.012)
            r = max(-band, min(band, r))
            new = on_tick(sym.exchange, close * (1 + r), close)
            o = on_tick(
                sym.exchange, close * (1 + max(-band, min(band, rng.gauss(0, 0.004)))), close
            )
            hi = on_tick(
                sym.exchange,
                min(max(o, new) * (1 + abs(rng.gauss(0, 0.006))), close * (1 + band)),
                close,
            )
            lo = on_tick(
                sym.exchange,
                max(min(o, new) * (1 - abs(rng.gauss(0, 0.006))), close * (1 - band)),
                close,
            )
            hi, lo = max(hi, o, new), min(lo, o, new)
            activity = 1 + 8 * abs(market[i])
            turnover = sym.turnover_vnd * math.exp(rng.gauss(0, 0.35)) * activity
            volume = max(100, int(turnover / new / 100) * 100)
            rows.append(row(sym.code, day, o, hi, lo, new, volume))
            if sym.turnover_vnd >= FLOW_MIN_TURNOVER_VND:
                value = volume * new
                for prefix, table, share in (
                    ("fr", "foreign_trade_daily", 0.12),
                    ("prop", "prop_trade_daily", 0.04),
                ):
                    net = value * share * (math.tanh(40 * r) * 0.5 + rng.gauss(0, 0.35))
                    buy = value * share + max(net, 0)
                    sell = buy - net
                    flows[table].append(flow(prefix, sym.code, day, buy, sell, new))
            close = new
    index = index_rows(days, market, rng)
    listed = [
        {
            "symbol": s.code,
            "exchange": "DELISTED"
            if s.last < n - 1
            else ("HSX" if s.exchange == "HOSE" else "HNX"),
            "type": "stock",
            "_source_sha256": "demo",
            "_loaded_at": LOADED_AT,
        }
        for s in symbols
    ]
    return rows, listed, flows, index, symbols


def flow(prefix: str, symbol: str, day: dt.date, buy: float, sell: float, price: int) -> dict:
    """Match = total, put-through 0, net = buy - sell, in value and in shares."""
    out = {"symbol": symbol, "session_date": day, "breakdown_valid": True, "source": "demo"}
    for side, val in (("buy", buy), ("sell", sell), ("net", buy - sell)):
        for unit, amount in (("val", round(val)), ("vol", round(val / price))):
            out[f"{prefix}_{side}_{unit}_matched"] = float(amount)
            out[f"{prefix}_{side}_{unit}_deal"] = 0.0
            out[f"{prefix}_{side}_{unit}_total"] = float(amount)
    out["breakdown_valid"] = True
    return {**out, "_source_sha256": "demo", "_loaded_at": LOADED_AT}


def index_rows(days: list[dt.date], market: list[float], rng: random.Random) -> list[dict]:
    out = []
    for code, level, beta in (
        ("VNINDEX", 1_180.0, 1.0),
        ("VN30", 1_220.0, 1.1),
        ("HNXINDEX", 230.0, 0.9),
    ):
        close = level
        for day, m in zip(days, market, strict=True):
            prev, close = close, close * (1 + beta * m)
            spread = abs(rng.gauss(0, 0.004))
            out.append(
                {
                    "index_code": code,
                    "session_date": day,
                    "open": round(prev, 2),
                    "high": round(max(prev, close) * (1 + spread), 2),
                    "low": round(min(prev, close) * (1 - spread), 2),
                    "close": round(close, 2),
                    "volume": int(rng.uniform(4e8, 9e8)),
                    "_source_id": "vnstock_quote",
                    "_source_sha256": "demo",
                    "_loaded_at": LOADED_AT,
                }
            )
    return out


def industry_rows(symbols: list[Symbol]) -> tuple[list[dict], list[dict]]:
    by_symbol, tree = [], {}
    for s in symbols:
        for level, (code, vi, en) in ((1, SECTORS[s.sector][0]), (2, SECTORS[s.sector][1])):
            tree[(code, level)] = (vi, en)
            by_symbol.append(
                {
                    "symbol": s.code,
                    "icb_level": level,
                    "icb_code": code,
                    "icb_name": vi,
                    "_source_sha256": "demo",
                    "_loaded_at": LOADED_AT,
                }
            )
    icb = [
        {
            "icb_name": vi,
            "en_icb_name": en,
            "icb_code": code,
            "level": level,
            "_source_sha256": "demo",
            "_loaded_at": LOADED_AT,
        }
        for (code, level), (vi, en) in sorted(tree.items())
    ]
    return by_symbol, icb


def membership_rows(rows: list[dict], symbols: list[Symbol], days: list[dt.date]) -> list[dict]:
    """VN30 / HNX30 at the last two sessions: the 30 largest by turnover on the exchange."""
    turnover: dict[str, float] = {}
    for r in rows:
        if r["session_date"] >= days[-20]:
            turnover[r["symbol"]] = turnover.get(r["symbol"], 0) + r["close_vnd"] * r["volume"]
    out = []
    for group, exchange in (("VN30", "HOSE"), ("HNX30", "HNX")):
        live = [s.code for s in symbols if s.exchange == exchange and s.last == len(days) - 1]
        top = sorted(live, key=lambda c: -turnover.get(c, 0))[:30]
        out += [
            {"as_of_date": d, "group_code": group, "symbol": c, "_loaded_at": LOADED_AT}
            for d in days[-2:]
            for c in top
        ]
    return out


def problems(rows: list[dict], symbols: list[Symbol]) -> list[str]:
    """Rows that would break a rule the warehouse checks: off the tick, outside the band,
    OHLC out of order, or a stale row that does not copy the previous close."""
    exchange = {s.code: s.exchange for s in symbols}
    out, previous = [], {}
    for r in sorted(rows, key=lambda r: (r["symbol"], r["session_date"])):
        sym, ex = r["symbol"], exchange[r["symbol"]]
        o, h, lo, c = r["open_vnd"], r["high_vnd"], r["low_vnd"], r["close_vnd"]
        where = f"{sym} {r['session_date']}"
        if not lo <= min(o, c) <= max(o, c) <= h:
            out.append(f"{where}: OHLC out of order")
        if any(v % tick(ex, v) for v in (o, h, lo, c)):
            out.append(f"{where}: off the tick")
        p = previous.get(sym)
        if p is not None:
            if (
                abs(c / p - 1) > BAND[ex] + 1e-9
                or h > p * (1 + BAND[ex])
                or lo < p * (1 - BAND[ex])
            ):
                out.append(f"{where}: outside the ±{BAND[ex]:.0%} band")
            if r["volume"] == 0 and not o == h == lo == c == p:
                out.append(f"{where}: stale row does not copy the previous close")
        previous[sym] = c
    return out


def build(out: Path, days: list[dt.date]) -> dict[str, int]:
    rows, listed, flows, index, symbols = generate(days)
    found = problems(rows, symbols)
    if found:
        raise ValueError(f"{len(found)} generated rows break a rule, e.g. {found[0]}")
    by_symbol, icb = industry_rows(symbols)
    project = copy_project(out, move_date=None)
    db = project / "target" / "ci.duckdb"
    db.parent.mkdir(parents=True, exist_ok=True)
    dbt_step(project, "run-operation", "create_ci_sources")
    tables = {
        "ohlcv_daily": rows,
        "ref_symbols_by_exchange": listed,
        "ref_symbols_by_industries": by_symbol,
        "ref_industries_icb": icb,
        "index_daily": index,
        "index_membership_snapshot": membership_rows(rows, symbols, days),
        **flows,
    }
    for table, table_rows in tables.items():
        load(db, table, table_rows, replace=True)
    dbt_step(project, "seed")
    dbt_step(project, "run")
    return {t: len(r) for t, r in tables.items()}


def self_test() -> int:
    import subprocess

    days = sessions(dt.date(2024, 1, 2), dt.date(2024, 3, 29))
    rows, listed, flows, index, symbols = generate(days)
    again = generate(days)[0]
    # planted: one session jumps 20 % (outside both bands), one price leaves the tick grid
    jump = [dict(r) for r in rows]
    k = next(
        i
        for i, r in enumerate(jump)
        if i > 10 and r["volume"] and jump[i - 1]["symbol"] == r["symbol"]
    )
    jump[k]["close_vnd"] = jump[k]["high_vnd"] = on_tick("HNX", jump[k - 1]["close_vnd"] * 1.2, 0)
    off = [dict(r) for r in rows]
    off[k]["close_vnd"] += 1
    one = flows["foreign_trade_daily"][0]
    by_symbol, icb = industry_rows(symbols)
    stale = [r for r in rows if r["volume"] == 0]
    bogus = subprocess.run(  # noqa: S603 - this script, fixed arguments
        [sys.executable, __file__, "--bogus"], capture_output=True, timeout=120, check=False
    ).returncode
    checks = {
        "sessions: no weekend, no seeded holiday": all(
            d.weekday() < 5 and d not in HOLIDAYS for d in days
        )
        and dt.date(2024, 2, 8) not in days,
        "200 symbols in 8 supersectors": len(symbols) == 200
        and len({s.sector for s in symbols}) == 8,
        "HNX symbols as configured": sum(s.exchange == "HNX" for s in symbols) == N_HNX,
        "every row keeps the tick, the band and the OHLC order": problems(rows, symbols) == [],
        "planted: a 20 % jump is caught as outside the band": any(
            "band" in p for p in problems(jump, symbols)
        ),
        "planted: a price off the tick is caught": any("tick" in p for p in problems(off, symbols)),
        "stale rows exist and copy the previous close": bool(stale),
        "deterministic for one seed": rows == again,
        "flows: net = buy - sell, match = total": one["fr_net_val_total"]
        == one["fr_buy_val_total"] - one["fr_sell_val_total"]
        and one["fr_buy_val_matched"] == one["fr_buy_val_total"],
        "three indices, one row per session each": len(index) == 3 * len(days),
        "two ICB levels per symbol": len(by_symbol) == 2 * len(symbols)
        and {r["level"] for r in icb} == {1, 2},
        "delisted symbols are listed as DELISTED": sum(r["exchange"] == "DELISTED" for r in listed)
        == N_DELISTED,
        "an unknown argument is refused with exit 2": bogus == 2,
    }
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out", type=Path, help="a new folder for the dbt project and the DuckDB file"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="generate, load and build")
    mode.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.out is None:
        parser.error("--out is required")
    days = sessions()
    if not args.apply:
        print(
            f"⚪ dry run: 200 symbols x {len(days)} sessions "
            f"({days[0]} to {days[-1]}) into {args.out}"
        )
        return 0
    if args.out.exists():
        print(f"🔴 cannot run: {args.out} exists; give a new folder", file=sys.stderr)
        return 2
    try:
        counts = build(args.out, days)
    except ValueError as exc:
        print(f"🔴 {exc}", file=sys.stderr)
        return 1
    except CannotRun as exc:
        print(f"🔴 cannot run: {exc}", file=sys.stderr)
        return 2
    print(f"✅ built {args.out / 'target' / 'ci.duckdb'}")
    for table, n in counts.items():
        print(f"   {table}: {n:,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
