"""Record a live market feed verbatim for a few minutes (spec S0, the cloud gate).

Every message is written as received, one JSON line each with `received_at` (UTC), next to
connection events (connected, disconnected, reconnected, connect_failed, finished) and the
process's RAM and CPU every `--stats-seconds`. Nothing is parsed here; `feed_report.py`
aggregates the file. The vendor's client library is imported only when the probe runs: it
is licensed per device and is not a dependency of this project, so the probe runs under the
interpreter that has it (spec S0.2).

Standalone on purpose (no import of this package), so it runs under that interpreter by
path. Time limits: the whole run, every connect attempt, every disconnect.

Exit codes: 0 = finished and at least one message recorded · 1 = no message recorded (the
feed did not deliver) · 2 = cannot run (bad arguments, the library or its licence missing).

Usage:
    python feed_probe.py --minutes 30 --symbols FPT,HPG,... --out <dir>
    python feed_probe.py --self-test
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

CONNECT_TIMEOUT_SECONDS = 30
DISCONNECT_TIMEOUT_SECONDS = 10
RECONNECT_WAIT_SECONDS = 5
HEALTH_POLL_SECONDS = 1.0


def iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).isoformat(timespec="milliseconds")


class Recorder:
    """Appends JSON lines; counts what it wrote."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.time) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a", encoding="utf-8")
        self.clock = clock
        self.messages = 0

    def _write(self, record: dict) -> None:
        self.handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def message(self, raw: Any) -> None:
        record = {"kind": "message", "received_at": iso(self.clock())}
        if isinstance(raw, bytes):
            record.update(raw=raw.decode("utf-8", errors="replace"), binary=True)
        else:
            record["raw"] = raw if isinstance(raw, str) else repr(raw)
        self._write(record)
        self.messages += 1

    def event(self, name: str, detail: str = "") -> None:
        self._write({"kind": "event", "event": name, "at": iso(self.clock()), "detail": detail})
        self.handle.flush()

    def stats(self, rss_mb: float, cpu_percent: float) -> None:
        self._write(
            {
                "kind": "stats",
                "at": iso(self.clock()),
                "rss_mb": round(rss_mb, 1),
                "cpu_percent": round(cpu_percent, 1),
            }
        )
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()


async def sample_stats(recorder: Recorder, every: float) -> None:
    try:
        import psutil
    except ImportError:
        recorder.event("stats_unavailable", "psutil not installed")
        return
    process = psutil.Process()
    process.cpu_percent()  # the first call only starts the measurement
    while True:
        await asyncio.sleep(every)
        recorder.stats(process.memory_info().rss / 2**20, process.cpu_percent())


async def probe(
    make_client: Callable[[], Any],
    recorder: Recorder,
    seconds: float,
    stats_every: float,
    connect_timeout: float = CONNECT_TIMEOUT_SECONDS,
    reconnect_wait: float = RECONNECT_WAIT_SECONDS,
) -> None:
    """Connect, record until `seconds` have passed, reconnect after a drop."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    stats = asyncio.create_task(sample_stats(recorder, stats_every))
    connected_once = False
    try:
        while loop.time() < deadline:
            client = make_client()
            try:
                await asyncio.wait_for(
                    client.connect(), timeout=min(connect_timeout, deadline - loop.time())
                )
            except Exception as exc:  # noqa: BLE001 - any failure to connect is recorded
                recorder.event("connect_failed", f"{type(exc).__name__}: {exc}"[:500])
                await asyncio.sleep(max(0.0, min(reconnect_wait, deadline - loop.time())))
                continue
            recorder.event("reconnected" if connected_once else "connected")
            connected_once = True
            while loop.time() < deadline and client.is_connected():
                await asyncio.sleep(min(HEALTH_POLL_SECONDS, max(0.0, deadline - loop.time())))
            if loop.time() < deadline:
                recorder.event("disconnected")
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.disconnect(), timeout=DISCONNECT_TIMEOUT_SECONDS)
    finally:
        stats.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stats
        recorder.event("finished", f"messages={recorder.messages}")


def vendor_client_factory(symbols: list[str], recorder: Recorder) -> Callable[[], Any]:
    """The licensed library's client, recording every raw message before any parsing."""
    from vnstock_pipeline.stream.sources.vps import WSSClient

    class RecordingClient(WSSClient):
        def _parse_message(self, message):  # noqa: ANN001 - the library's signature
            recorder.message(message)
            return None  # nothing downstream: aggregation is feed_report.py's job

    def make() -> Any:
        client = RecordingClient(enable_session_manager=False)
        client.subscribe_symbols(symbols)
        return client

    return make


# --- self-test -----------------------------------------------------------------------------


class FakeClient:
    """Delivers scripted messages to the recorder, then optionally drops the connection."""

    def __init__(
        self, recorder: Recorder, messages: list[Any], drop_after: float | None, fail: bool = False
    ) -> None:
        self.recorder, self.messages, self.drop_after, self.fail = (
            recorder,
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
            await asyncio.sleep(0.01)
            self.recorder.message(m)
        if self.drop_after is not None:
            await asyncio.sleep(self.drop_after)
            self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    async def disconnect(self) -> None:
        self.connected = False
        if self.task:
            self.task.cancel()


def self_test() -> int:
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.jsonl"
        recorder = Recorder(path)
        script = iter(
            [
                ("fail", []),  # planted: refused once
                ("ok", ['42["stock",{"a":1}]', b"\xff\xfebinary", "not json at all"]),  # then drops
                ("ok", ['42["index",{"b":2}]']),  # reconnected, stays up
            ]
        )

        def make() -> FakeClient:
            kind, msgs = next(script, ("ok", []))
            return FakeClient(
                recorder,
                msgs,
                drop_after=0.3
                if kind == "ok" and msgs and msgs[0].startswith('42["stock"')
                else None,
                fail=kind == "fail",
            )

        started = time.monotonic()
        asyncio.run(probe(make, recorder, seconds=2.0, stats_every=0.5, reconnect_wait=0.1))
        elapsed = time.monotonic() - started
        recorder.close()
        lines = [json.loads(x) for x in path.read_text("utf-8").splitlines()]
    events = [x["event"] for x in lines if x["kind"] == "event"]
    connection = [e for e in events if e != "stats_unavailable"]  # psutil may be absent
    messages = [x for x in lines if x["kind"] == "message"]
    stamps = [x["received_at"] for x in messages]
    checks = {
        "every message is recorded verbatim, malformed ones too": [m["raw"] for m in messages][:1]
        == ['42["stock",{"a":1}]']
        and len(messages) == 4
        and "not json at all" in [m["raw"] for m in messages],
        "a binary message is kept, decoded with a flag": any(m.get("binary") for m in messages),
        "received_at is recorded and never goes back": stamps == sorted(stamps),
        "planted refusal, drop and reconnect are all recorded in order": connection[:4]
        == ["connect_failed", "connected", "disconnected", "reconnected"],
        "the run ends at its limit and says so": events[-1] == "finished" and elapsed < 4.0,
        "process RAM and CPU are sampled": any(x["kind"] == "stats" for x in lines)
        or "stats_unavailable" in events,
        "an unknown argument is rejected with exit 2": subprocess.run(  # noqa: S603 - this script, fixed arguments
            [sys.executable, __file__, "--bogus"], capture_output=True, timeout=120, check=False
        ).returncode
        == 2,
    }
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--minutes", type=float, help="how long to record")
    parser.add_argument("--symbols", help="comma-separated symbols to subscribe")
    parser.add_argument("--out", type=Path, help="output folder (raw messages: keep it local)")
    parser.add_argument("--stats-seconds", type=float, default=30.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not (args.minutes and args.symbols and args.out):
        parser.error("--minutes, --symbols and --out are required")
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    path = args.out / f"probe_{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}.jsonl"
    recorder = Recorder(path)
    try:
        make = vendor_client_factory(symbols, recorder)
    except (ImportError, SystemExit) as exc:  # the library exits at import without a licence
        recorder.event("cannot_run", f"{type(exc).__name__}: {exc}")
        recorder.close()
        print(f"⚪ not run: the feed library or its licence is missing ({exc})", file=sys.stderr)
        return 2
    recorder.event("started", f"symbols={len(symbols)} minutes={args.minutes}")
    try:
        asyncio.run(probe(make, recorder, args.minutes * 60, args.stats_seconds))
    finally:
        recorder.close()
    print(f"{recorder.messages} messages -> {path}")
    return 0 if recorder.messages else 1


if __name__ == "__main__":
    sys.exit(main())
