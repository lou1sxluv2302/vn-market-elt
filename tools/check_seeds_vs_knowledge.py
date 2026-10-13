"""Check that the market-rule seeds say what the knowledge file says.

docs/knowledge/market-microstructure.md is v2's source of truth for market rules
(ADR-0021); dbt/seeds/*.csv are their machine form. This reads both and compares:
- tick sizes (§4 table) against tick_size.csv, stock rows;
- normal-day price bands (§3 table) against price_band.csv;
- holidays (§8, the 2026 and 2027 tables, date ranges expanded to weekdays) against
  holidays.csv, with the statuses the file names (2027 provisional).

Exit codes: 0 = they agree · 1 = they disagree · 2 = a file cannot be read or parsed.

Usage:
    python tools/check_seeds_vs_knowledge.py
    python tools/check_seeds_vs_knowledge.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from vnmarket.common.config import REPO_ROOT, utf8_stdio

KNOWLEDGE = REPO_ROOT / "docs" / "knowledge" / "market-microstructure.md"
SEEDS = REPO_ROOT / "dbt" / "seeds"


class ParseError(Exception):
    """The knowledge file no longer has the shape this check reads."""


def section(text: str, heading: str) -> str:
    """The section under `heading`, subsections included, up to the next heading of the
    same or a higher level."""
    start = re.search(rf"^(#+) {re.escape(heading)}", text, re.M)
    if not start:
        raise ParseError(f"section not found: {heading}")
    level = len(start.group(1))
    end = re.compile(rf"^#{{1,{level}}} ", re.M).search(text, start.end())
    return text[start.start() : end.start() if end else len(text)]


def table_rows(block: str) -> list[list[str]]:
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in block.splitlines()
        if line.strip().startswith("|")
    ]
    return [r for r in rows if not set("".join(r)) <= set("-: ")][1:]  # drop header, rule


def knowledge_ticks(text: str) -> dict[tuple[str, int], int]:
    """{(exchange, price_from_vnd): tick_vnd} for stocks, from the §4 table."""
    rows = table_rows(section(text, "4. Tick size and lots").split("| Lot rule")[0])
    exchanges = ["HOSE", "HNX", "UPCOM"]
    ticks: dict[tuple[str, int], int] = {}
    for row in rows:
        price = row[0].replace(",", "")
        floors = re.findall(r"\d+", price)
        if not floors or row[0][0] not in "<≥0123456789":
            continue
        price_from = 0 if price.startswith("<") else int(floors[0])
        for exchange, cell in zip(exchanges, row[1:4], strict=True):
            if cell.isdigit():
                ticks[(exchange, price_from)] = int(cell)
    if not ticks:
        raise ParseError("no tick rows in §4")
    return ticks


def collapse(ticks: dict[tuple[str, int], int]) -> dict[tuple[str, int], int]:
    """Drop a price level whose tick equals the level below it: a flat 100 written once or
    three times is the same rule."""
    kept: dict[tuple[str, int], int] = {}
    previous: dict[str, int] = {}
    for (exchange, price_from), tick in sorted(ticks.items()):
        if previous.get(exchange) != tick:
            kept[(exchange, price_from)] = tick
        previous[exchange] = tick
    return kept


def knowledge_bands(text: str) -> dict[str, float]:
    """{exchange: ratio} for a normal day, from the §3 table."""
    for row in table_rows(section(text, "3. Price bands")):
        if row[0].lower().startswith("normal day"):
            values = [float(re.findall(r"[\d.]+", c)[0]) / 100 for c in row[1:4]]
            return dict(zip(["HOSE", "HNX", "UPCOM"], values, strict=True))
    raise ParseError("no normal-day row in §3")


def expand(year: int, cell: str) -> list[dt.date]:
    """'02-16 → 02-20 (Mon-Fri)', '01-01 (Thu)', '02-04, 02-05': weekdays it names."""
    cell = re.sub(r"\([^)]*\)", "", cell).replace("**", "")
    found = re.findall(r"(?<![\d-])(?:(\d{4})-)?(\d\d)-(\d\d)(?!\d)", cell)
    dates = [dt.date(int(y) if y else year, int(m), int(d)) for y, m, d in found]
    if "→" in cell and len(dates) == 2:
        start, end = dates
        dates = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    return [x for x in dates if x.weekday() < 5]


def knowledge_holidays(text: str) -> dict[dt.date, str]:
    """{date: expected status} from the §8 tables (2026 and 2027)."""
    block = section(text, "8. Trading calendar and holidays")
    found: dict[dt.date, str] = {}
    for year, status in ((2026, None), (2027, "provisional")):
        sub = re.search(rf"^### {year}.*?(?=^### |\Z)", block, re.M | re.S)
        if not sub:
            raise ParseError(f"no {year} table in §8")
        for row in table_rows(sub.group(0)):
            if len(row) < 2:
                continue
            for day in expand(year, row[1]):
                found[day] = status or ("announced" if "Culture" in row[0] else "confirmed")
    return found


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def compare(knowledge_path: Path, seeds_dir: Path) -> list[str]:
    text = knowledge_path.read_text(encoding="utf-8")
    problems = []

    want_ticks = knowledge_ticks(text)
    have_ticks = {
        (r["exchange"], int(r["price_from_vnd"])): int(r["tick_vnd"])
        for r in read_csv(seeds_dir / "tick_size.csv")
        if r["instrument_class"] == "stock"
    }
    want_ticks, have_ticks = collapse(want_ticks), collapse(have_ticks)
    if want_ticks != have_ticks:
        problems.append(f"tick_size: knowledge {want_ticks} != seed {have_ticks}")

    want_bands = knowledge_bands(text)
    have_bands = {
        r["exchange"]: float(r["band_ratio"])
        for r in read_csv(seeds_dir / "price_band.csv")
        if r["band_case"] == "normal"
    }
    if want_bands != have_bands:
        problems.append(f"price_band normal: knowledge {want_bands} != seed {have_bands}")

    want_days = knowledge_holidays(text)
    have_days = {
        dt.date.fromisoformat(r["holiday_date"]): r["status"]
        for r in read_csv(seeds_dir / "holidays.csv")
    }
    for day in sorted(set(want_days) | set(have_days)):
        if want_days.get(day) != have_days.get(day):
            problems.append(
                f"holiday {day}: knowledge {want_days.get(day)}, seed {have_days.get(day)}"
            )
    return problems


def self_test() -> int:
    """The real files agree (control); a planted change in a seed copy is caught."""
    checks = {
        "control: the committed knowledge file and seeds agree": compare(KNOWLEDGE, SEEDS) == []
    }
    with tempfile.TemporaryDirectory() as tmp:
        for name, old, new, label in (
            ("tick_size.csv", "HOSE,stock,10000,50,", "HOSE,stock,10000,20,", "tick"),
            ("price_band.csv", "HNX,normal,0.10,", "HNX,normal,0.15,", "band"),
            (
                "holidays.csv",
                "2026-11-24,culture_day,announced",
                "2026-11-25,culture_day,announced",
                "holiday",
            ),
        ):
            copy = Path(tmp) / label
            copy.mkdir()
            for f in SEEDS.glob("*.csv"):
                (copy / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            target = copy / name
            text = target.read_text(encoding="utf-8")
            if old not in text:  # the plant must change something, or the test proves nothing
                raise ParseError(f"{name}: planted text not found")
            target.write_text(text.replace(old, new), encoding="utf-8")
            problems = compare(KNOWLEDGE, copy)
            checks[f"planted {label} change in the seed is caught"] = (
                bool(problems)
                and all(p.startswith(("tick_size", "price_band", "holiday")) for p in problems)
                and {p.split()[0].rstrip(":") for p in problems}
                <= {"tick": {"tick_size"}, "band": {"price_band"}, "holiday": {"holiday"}}[label]
            )
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
    try:
        problems = compare(KNOWLEDGE, SEEDS)
    except (OSError, ParseError, KeyError, ValueError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2
    for line in problems:
        print(f"     {line}")
    print(f"{'🔴' if problems else '✅'} seeds agree with market-microstructure.md")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
