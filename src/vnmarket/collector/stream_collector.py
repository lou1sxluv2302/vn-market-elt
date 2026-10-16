"""Collect the intraday feed into 60-second parquet batches in a local spool (spec S1).

Every message is kept verbatim - parsing is dbt's job (S3) - one row each: `payload`
(the message as text; binary messages decoded with replacement and flagged), `is_binary`,
`received_at` (UTC), `batch_id` and `seq` (order within the batch). Each batch window of
`batch_seconds` becomes one file, written atomically, `dt=YYYY-MM-DD/batch=HHMMSS-<run>.parquet`
(Vietnam date and time of the window's start; `<run>` is the collector's start time, so a
restart within a minute never reuses a name). An empty window writes no file.
`uploader.py` moves the spool to the raw bucket.

The feed library is licensed per device and is not a dependency of this project: it is
imported only when the collector runs (as in `feed_probe.py`). Time limits: every connect
and disconnect; reconnects back off; the run stops at `--until` (default: the session's
stop time). Logs carry counts and error codes only (spec §14.4).

Calendar: weekends and holidays the seed marks `confirmed` are skipped; an `announced` or a
`provisional` holiday or a day with no row runs anyway - a missed real session is lost
forever, an unneeded run costs one warning (spec S1).

Exit codes: 0 = ran and wrote at least one batch · 1 = ran and wrote nothing (the feed
delivered nothing) · 2 = cannot run (arguments, config, the library or its licence) ·
3 = not a session day (skipped; systemd treats it as success).

Usage:
    python -m vnmarket.collector.stream_collector --symbols FPT,HPG [--until 15:05]
    python -m vnmarket.collector.stream_collector --symbols-file universe.txt --spool DIR
    python -m vnmarket.collector.stream_collector --self-test
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import datetime as dt
import json
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq

from vnmarket.common.config import REPO_ROOT, load_config, utf8_stdio

HOLIDAYS_SEED = REPO_ROOT / "dbt" / "seeds" / "holidays.csv"
SKIP_STATUSES = {"confirmed"}  # announced and provisional dates run anyway
HEALTH_POLL_SECONDS = 1.0
EXIT_NOT_A_SESSION = 3
SCHEMA = pa.schema(
    [
        ("payload", pa.string()),
        ("is_binary", pa.bool_()),
        ("received_at", pa.timestamp("ms", tz="UTC")),
        ("batch_id", pa.string()),
        ("seq", pa.int32()),
    ]
)


def log_event(event: str, **fields: Any) -> None:
    """One JSON line per event: counts and codes, never message content."""
    print(json.dumps({"event": event, **fields}), flush=True)


# --- calendar ---------------------------------------------------------------------------


def holidays_to_skip(seed: Path = HOLIDAYS_SEED) -> set[dt.date]:
    with seed.open(encoding="utf-8", newline="") as handle:
        return {
            dt.date.fromisoformat(r["holiday_date"])
            for r in csv.DictReader(handle)
            if r["status"] in SKIP_STATUSES
        }


def is_session_day(day: dt.date, skip: set[dt.date], weekdays: list[str]) -> bool:
    return day.strftime("%a").upper() in weekdays and day not in skip


# --- batching ---------------------------------------------------------------------------


class Batcher:
    """Buffers messages and writes one parquet file per completed window."""

    def __init__(
        self,
        spool: Path,
        seconds: float,
        tz: ZoneInfo,
        run_id: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.spool, self.seconds, self.tz, self.run_id, self.clock = (
            spool,
            seconds,
            tz,
            run_id,
            clock,
        )
        self.rows: list[tuple[str, bool, float]] = []
        self.window: float | None = None
        self.lock = threading.Lock()  # the library may deliver from its own thread
        self.messages = 0
        self.files: list[Path] = []

    def add(self, raw: Any) -> None:
        if isinstance(raw, bytes):
            payload, binary = raw.decode("utf-8", errors="replace"), True
        else:
            payload, binary = (raw if isinstance(raw, str) else repr(raw)), False
        with self.lock:
            now = self.clock()
            self._roll(now)
            self.rows.append((payload, binary, now))
            self.messages += 1

    def tick(self) -> None:
        """Write the window that has ended, if any; called about once a second."""
        with self.lock:
            self._roll(self.clock())

    def close(self) -> None:
        with self.lock:
            self._write()

    def _roll(self, now: float) -> None:
        window = now - now % self.seconds
        if self.window is not None and window != self.window:
            self._write()
        self.window = window

    def _write(self) -> None:
        rows, self.rows = self.rows, []
        if not rows or self.window is None:
            return
        start = dt.datetime.fromtimestamp(self.window, self.tz)
        batch_id = f"{start:%Y%m%dT%H%M%S}-{self.run_id}"
        target = self.spool / f"dt={start:%Y-%m-%d}" / f"batch={start:%H%M%S}-{self.run_id}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        table = pa.table(
            {
                "payload": [r[0] for r in rows],
                "is_binary": [r[1] for r in rows],
                "received_at": [int(r[2] * 1000) for r in rows],
                "batch_id": [batch_id] * len(rows),
                "seq": list(range(len(rows))),
            },
            schema=SCHEMA,
        )
        partial = target.with_suffix(".parquet.tmp")  # the uploader ignores it
        pq.write_table(table, partial)
        partial.replace(target)
        self.files.append(target)
        log_event("batch_written", batch_id=batch_id, messages=len(rows))


# --- the session ------------------------------------------------------------------------


async def collect(
    make_client: Callable[[], Any],
    batcher: Batcher,
    seconds: float,
    limits: dict,
) -> None:
    """Connect, keep the batches rolling until `seconds` pass, reconnect with back-off."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    failures = 0
    connected_once = False
    try:
        while loop.time() < deadline:
            client = make_client()
            try:
                await asyncio.wait_for(
                    client.connect(),
                    timeout=min(limits["connect_timeout_seconds"], deadline - loop.time()),
                )
            except Exception as exc:  # noqa: BLE001 - any failure to connect is retried
                failures += 1
                wait = min(
                    limits["reconnect_max_seconds"],
                    limits["reconnect_initial_seconds"] * 2 ** (failures - 1),
                )
                log_event("connect_failed", error=type(exc).__name__, retry_in_seconds=wait)
                await _sleep_ticking(batcher, min(wait, max(0.0, deadline - loop.time())))
                continue
            failures = 0
            log_event("reconnected" if connected_once else "connected")
            connected_once = True
            while loop.time() < deadline and client.is_connected():
                await _sleep_ticking(batcher, min(HEALTH_POLL_SECONDS, deadline - loop.time()))
            if loop.time() < deadline:
                log_event("disconnected")
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    client.disconnect(), timeout=limits["disconnect_timeout_seconds"]
                )
    finally:
        batcher.close()
        log_event("finished", messages=batcher.messages, batches=len(batcher.files))


async def _sleep_ticking(batcher: Batcher, seconds: float) -> None:
    end = asyncio.get_running_loop().time() + max(0.0, seconds)
    while (left := end - asyncio.get_running_loop().time()) > 0:
        await asyncio.sleep(min(HEALTH_POLL_SECONDS, left))
        batcher.tick()


def vendor_client_factory(symbols: list[str], batcher: Batcher) -> Callable[[], Any]:
    """The licensed library's client; every raw message goes to the batcher unparsed."""
    from vnstock_pipeline.stream.sources.vps import WSSClient

    class BatchingClient(WSSClient):
        def _parse_message(self, message):  # noqa: ANN001 - the library's signature
            batcher.add(message)
            return None  # nothing downstream: parsing is dbt's job

    def make() -> Any:
        client = BatchingClient(enable_session_manager=False)
        client.subscribe_symbols(symbols)
        return client

    return make


# --- self-test --------------------------------------------------------------------------


class FakeClient:
    """Delivers scripted messages to the batcher, then optionally drops the connection."""

    def __init__(self, batcher: Batcher, messages: list, drop_after: float | None, fail=False):
        self.batcher, self.messages, self.drop_after, self.fail = (
            batcher,
            messages,
            drop_after,
            fail,
        )
        self.connected = False
        self.task: asyncio.Task | None = None

    async def connect(self) -> None:
        if self.fail:
            raise ConnectionError("planted refusal")
        self.connected = True
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        for m in self.messages:
            await asyncio.sleep(0.05)
            self.batcher.add(m)
        if self.drop_after is not None:
            await asyncio.sleep(self.drop_after)
            self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    async def disconnect(self) -> None:
        self.connected = False
        if self.task:
            self.task.cancel()


def read_spool(spool: Path) -> pa.Table:
    files = sorted(spool.rglob("*.parquet"))
    return pa.concat_tables([pq.read_table(f) for f in files]) if files else SCHEMA.empty_table()


def self_test() -> int:
    import subprocess
    import tempfile

    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory() as tmp:
        # 1. Windows on a fake clock: 09:00:00 Vietnam time = 02:00:00 UTC.
        t0 = dt.datetime(2026, 10, 19, 2, 0, tzinfo=dt.UTC).timestamp()
        now = [t0]
        spool = Path(tmp) / "a"
        b = Batcher(spool, 60, tz, "090000", clock=lambda: now[0])
        for offset, raw in [(0.5, '42["a",1]'), (30, b"\xff\xfe"), (59.9, "not json")]:
            now[0] = t0 + offset
            b.add(raw)
        now[0] = t0 + 60.1
        b.tick()  # the first window has ended
        first = list(spool.rglob("*.parquet"))
        now[0] = t0 + 170  # a silent minute (60-120), then a message at 120-180
        b.tick()
        b.add("late")
        b.close()
        files = sorted(spool.rglob("*.parquet"))
        table = read_spool(spool)
        checks["a window's batch is written when the window ends, named in Vietnam time"] = [
            f.relative_to(spool).as_posix() for f in first
        ] == ["dt=2026-10-19/batch=090000-090000.parquet"]
        checks["a silent minute writes no file; close flushes the last window"] = [
            f.name for f in files
        ] == ["batch=090000-090000.parquet", "batch=090200-090000.parquet"]
        checks["every message verbatim, binary flagged, seq in order"] = (
            table.column("payload").to_pylist()[:1] == ['42["a",1]']
            and table.column("is_binary").to_pylist() == [False, True, False, False]
            and table.column("seq").to_pylist() == [0, 1, 2, 0]
            and table.schema == SCHEMA
        )
        checks["no partial file is left behind"] = not list(spool.rglob("*.tmp"))

        # 2. A real session on a 1-second window: refusal, drop, reconnect, nothing lost.
        spool2 = Path(tmp) / "b"
        live = Batcher(spool2, 1, tz, "run")
        sent = [f"m{i}" for i in range(12)]
        script = iter([("fail", []), ("ok", sent[:6]), ("ok", sent[6:])])

        def make() -> FakeClient:
            kind, msgs = next(script, ("ok", []))
            return FakeClient(
                live, msgs, drop_after=0.2 if msgs == sent[:6] else None, fail=kind == "fail"
            )

        limits = {
            "connect_timeout_seconds": 5,
            "disconnect_timeout_seconds": 5,
            "reconnect_initial_seconds": 0.1,
            "reconnect_max_seconds": 0.2,
        }
        started = time.monotonic()
        asyncio.run(collect(make, live, 3.5, limits))
        elapsed = time.monotonic() - started
        got = read_spool(spool2).column("payload").to_pylist()
        checks["across a refusal and a drop every message lands exactly once"] = (
            sorted(got) == sorted(sent) and len(live.files) >= 2
        )
        checks["the session stops at its limit"] = elapsed < 6.0

        # 3. The session ends inside a window: only the flush at stop can write it.
        spool3 = Path(tmp) / "c"
        short = Batcher(spool3, 60, tz, "run")
        asyncio.run(
            collect(lambda: FakeClient(short, ["x", "y"], drop_after=None), short, 0.5, limits)
        )
        checks["stopping inside a window still writes what it holds"] = read_spool(spool3).column(
            "payload"
        ).to_pylist() == ["x", "y"]

    skip = {dt.date(2026, 11, 24)}
    checks["calendar: a skipped holiday, a weekend, and a day without a row"] = (
        not is_session_day(dt.date(2026, 11, 24), skip, ["MON", "TUE", "WED", "THU", "FRI"])
        and not is_session_day(dt.date(2026, 10, 17), skip, ["MON", "TUE", "WED", "THU", "FRI"])
        and is_session_day(dt.date(2026, 10, 19), skip, ["MON", "TUE", "WED", "THU", "FRI"])
    )
    seed_skip = holidays_to_skip()
    checks["calendar: the seed's confirmed dates skip; announced and provisional ones run"] = (
        dt.date(2026, 2, 17) in seed_skip and dt.date(2027, 1, 1) not in seed_skip
    )
    checks["an unknown argument is rejected with exit 2"] = (
        subprocess.run(  # noqa: S603 - this module, fixed arguments
            [sys.executable, "-m", "vnmarket.collector.stream_collector", "--bogus"],
            capture_output=True,
            timeout=120,
            check=False,
        ).returncode
        == 2
    )
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


# --- command line -----------------------------------------------------------------------


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--symbols", help="comma-separated symbols to subscribe")
    parser.add_argument("--symbols-file", type=Path, help="one symbol per line")
    parser.add_argument("--spool", type=Path, help="local spool directory (default: config)")
    parser.add_argument("--until", help="stop at this Vietnam time, HH:MM (default: config)")
    parser.add_argument("--ignore-calendar", action="store_true", help="run on any day")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    cfg = load_config("collector")
    tz = ZoneInfo(cfg["timezone"])
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    elif args.symbols_file:
        symbols = [s.strip().upper() for s in args.symbols_file.read_text("utf-8").split()]
    else:
        parser.error("--symbols or --symbols-file is required")
    now = dt.datetime.now(tz)
    if not args.ignore_calendar and not is_session_day(
        now.date(), holidays_to_skip(), cfg["schedule"]["weekdays"]
    ):
        print(f"⚪ not a session day: {now.date()} (weekend or seeded holiday)")
        return EXIT_NOT_A_SESSION
    hour, minute = map(int, (args.until or cfg["schedule"]["stop_local"]).split(":"))
    stop = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    seconds = (stop - now).total_seconds()
    if seconds <= 0:
        parser.error(f"--until {stop:%H:%M} has already passed")
    spool = args.spool or REPO_ROOT / cfg["spool_dir"]
    batcher = Batcher(spool, cfg["batch_seconds"], tz, f"{now:%H%M%S}")
    try:
        make = vendor_client_factory(symbols, batcher)
    except (ImportError, SystemExit) as exc:  # the library exits at import without a licence
        print(f"⚪ not run: the feed library or its licence is missing ({exc})", file=sys.stderr)
        return 2
    log_event("started", symbols=len(symbols), stop=f"{stop:%H:%M}")
    asyncio.run(collect(make, batcher, seconds, cfg))
    return 0 if batcher.files else 1


if __name__ == "__main__":
    sys.exit(main())
