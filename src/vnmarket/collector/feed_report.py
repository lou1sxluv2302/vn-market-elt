"""Aggregate a feed probe's output into the numbers the S0 gate needs (aggregates only).

Reads the JSON lines `feed_probe.py` wrote and prints one JSON summary: messages and bytes
per type, messages and MB per minute (mean and peak), connection events, peak RAM and mean
CPU, and the field names seen per message type (to tell which data the feed carries). No
message content or value leaves this summary. Socket.IO framing: an event message is the
packet "42" followed by a JSON array whose first element names the event; anything else is
counted as a control packet by its leading digits.

Standalone (no import of this package), like the probe.

Exit codes: 0 = summary printed · 1 = the file holds no message · 2 = cannot read it.

Usage:
    python feed_report.py <probe.jsonl> [--out summary.json]
    python feed_report.py --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


def message_type(raw: str) -> tuple[str, dict | None]:
    """(type, payload dict or None) of one raw message."""
    if raw.startswith("42"):
        try:
            body = json.loads(raw[2:])
        except json.JSONDecodeError:
            return "malformed", None
        if isinstance(body, list) and body and isinstance(body[0], str):
            payload = body[1] if len(body) > 1 else None
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = None
            if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                payload = payload["data"]
            return body[0], payload if isinstance(payload, dict) else None
        return "malformed", None
    lead = re.match(r"\d+", raw)
    return (f"control:{lead.group(0)}" if lead else "malformed"), None


def summarise(lines: list[dict]) -> dict:
    counts: Counter = Counter()
    sizes: Counter = Counter()
    keys: dict[str, set] = defaultdict(set)
    per_minute: Counter = Counter()
    bytes_minute: Counter = Counter()
    events: Counter = Counter()
    rss, cpu = [], []
    for x in lines:
        if x["kind"] == "message":
            kind, payload = message_type(x["raw"])
            size = len(x["raw"].encode("utf-8"))
            counts[kind] += 1
            sizes[kind] += size
            minute = x["received_at"][:16]
            per_minute[minute] += 1
            bytes_minute[minute] += size
            if payload:
                keys[kind].update(payload)
        elif x["kind"] == "event":
            events[x["event"]] += 1
        elif x["kind"] == "stats":
            rss.append(x["rss_mb"])
            cpu.append(x["cpu_percent"])
    minutes = sorted(per_minute)
    first = dt.datetime.fromisoformat(minutes[0]) if minutes else None
    last = dt.datetime.fromisoformat(minutes[-1]) if minutes else None
    span = int((last - first).total_seconds() // 60) + 1 if minutes else 0
    full = (
        [
            per_minute.get((first + dt.timedelta(minutes=i)).isoformat(timespec="minutes"), 0)
            for i in range(span)
        ]
        if minutes
        else []
    )
    full_bytes = (
        [
            bytes_minute.get((first + dt.timedelta(minutes=i)).isoformat(timespec="minutes"), 0)
            for i in range(span)
        ]
        if minutes
        else []
    )
    return {
        "messages": sum(counts.values()),
        "minutes_observed": span,
        "messages_per_minute": {
            "mean": round(statistics.mean(full), 1) if full else 0,
            "peak": max(full, default=0),
            "silent_minutes": sum(1 for v in full if v == 0),
        },
        "mb_per_minute": {
            "mean": round(statistics.mean(full_bytes) / 2**20, 3) if full_bytes else 0,
            "peak": round(max(full_bytes, default=0) / 2**20, 3),
        },
        "by_type": {
            k: {"messages": counts[k], "bytes": sizes[k], "fields": sorted(keys.get(k, ()))}
            for k in sorted(counts)
        },
        "events": dict(events),
        "rss_mb_peak": max(rss, default=None),
        "cpu_percent_mean": round(statistics.mean(cpu), 1) if cpu else None,
    }


def self_test() -> int:
    import subprocess

    def msg(minute: str, raw: str) -> dict:
        return {
            "kind": "message",
            "received_at": f"2026-10-19T02:{minute}:05.000+00:00",
            "raw": raw,
        }

    lines = [
        {"kind": "event", "event": "connected"},
        msg("30", '42["stock",{"sym":"AAA","lastPrice":10}]'),
        msg("30", '42["stock","{\\"data\\":{\\"sym\\":\\"BBB\\",\\"r\\":9}}"]'),
        msg("30", "3"),
        msg("32", '42["index",{"mc":"10"}]'),
        msg("32", "42[broken"),
        {"kind": "event", "event": "disconnected"},
        {"kind": "event", "event": "reconnected"},
        {"kind": "stats", "rss_mb": 80.0, "cpu_percent": 2.0},
        {"kind": "stats", "rss_mb": 95.5, "cpu_percent": 4.0},
    ]
    s = summarise(lines)
    checks = {
        "messages counted by type, framing and malformed ones apart": {
            k: v["messages"] for k, v in s["by_type"].items()
        }
        == {"control:3": 1, "index": 1, "malformed": 1, "stock": 2},
        "field names from object and string payloads (data unwrapped)": s["by_type"]["stock"][
            "fields"
        ]
        == ["lastPrice", "r", "sym"],
        "a silent minute inside the run is counted": s["minutes_observed"] == 3
        and s["messages_per_minute"]["silent_minutes"] == 1
        and s["messages_per_minute"]["peak"] == 3,
        "events and resources aggregated": s["events"]
        == {"connected": 1, "disconnected": 1, "reconnected": 1}
        and s["rss_mb_peak"] == 95.5
        and s["cpu_percent_mean"] == 3.0,
        "no value leaves the summary": "AAA" not in json.dumps(s) and "BBB" not in json.dumps(s),
        "an unknown argument is rejected with exit 2": subprocess.run(  # noqa: S603 - this script
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
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.path:
        parser.error("a probe file is required")
    try:
        lines = [json.loads(x) for x in args.path.read_text("utf-8").splitlines() if x.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2
    summary = summarise(lines)
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, "utf-8")
    print(text)
    return 0 if summary["messages"] else 1


if __name__ == "__main__":
    sys.exit(main())
