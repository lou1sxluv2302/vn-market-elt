"""Reconcile one session's stream batches: GCS against BigQuery, batch by batch (spec S2).

Every object under `<prefix>/dt=<date>/` in the raw bucket carries its message count as
metadata (`messages`, set by the uploader). Each must have a `batch_id` in the stream table
with exactly that many rows, and the table must hold no batch of that date without an
object. One query a day (with a partition filter on the session's day).

Runs as the owner (application-default credentials), who can read both the bucket and
the table; the collector's own account can read neither back.

Exit codes: 0 = every batch equal · 1 = a batch missing, extra or unequal · 2 = cannot run
(config, access) · 3 = nothing to compare (no batch in either place: not a pass).

Usage:
    python tools/reconcile_stream.py --date 2026-10-19
    python tools/reconcile_stream.py --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

from vnmarket.common.config import load_config, load_env, utf8_stdio

QUERY_TIMEOUT_SECONDS = 300
OBJECT = re.compile(r"dt=(\d{4})-(\d{2})-(\d{2})/batch=(\d{6})-(\w+)\.parquet$")


def batch_id_of(object_name: str) -> str | None:
    """`.../dt=2026-10-19/batch=090000-085500.parquet` -> `20261019T090000-085500`."""
    m = OBJECT.search(object_name)
    return f"{m[1]}{m[2]}{m[3]}T{m[4]}-{m[5]}" if m else None


def compare(in_gcs: dict[str, int | None], in_bq: dict[str, int]) -> dict[str, list[str]]:
    """Batch ids by outcome; `None` in GCS means the object has no message count."""
    out: dict[str, list[str]] = {
        "equal": [],
        "unequal": [],
        "missing_in_bigquery": [],
        "missing_in_gcs": [],
        "no_count_in_gcs": [],
    }
    for batch in sorted(set(in_gcs) | set(in_bq)):
        if batch not in in_gcs:
            out["missing_in_gcs"].append(batch)
        elif in_gcs[batch] is None:
            out["no_count_in_gcs"].append(batch)
        elif batch not in in_bq:
            out["missing_in_bigquery"].append(batch)
        elif in_gcs[batch] == in_bq[batch]:
            out["equal"].append(batch)
        else:
            out["unequal"].append(batch)
    return out


def verdict(result: dict[str, list[str]]) -> int:
    if not any(result.values()):
        return 3
    return 0 if all(not v for k, v in result.items() if k != "equal") else 1


def run(day: dt.date) -> int:
    from google.cloud import bigquery, storage

    cfg, env = load_config("collector"), load_env()
    project, up = env["gcp"]["project_id"], cfg["upload"]
    prefix = f"{up['prefix']}/dt={day.isoformat()}/"
    in_gcs: dict[str, int | None] = {}
    blobs = storage.Client(project=project).list_blobs(
        env["gcp"]["raw_bucket"], prefix=prefix, timeout=QUERY_TIMEOUT_SECONDS
    )
    for blob in blobs:
        batch = batch_id_of(blob.name)
        if batch:
            count = (blob.metadata or {}).get("messages")
            in_gcs[batch] = int(count) if count is not None else None
    tz = ZoneInfo(cfg["timezone"])
    start = dt.datetime.combine(day, dt.time(), tz)
    client = bigquery.Client(project=project)
    job = client.query(
        f"select batch_id, count(*) as n from `{project}.{up['load_table']}` "  # noqa: S608 - names from config
        "where received_at >= @start and received_at < @end group by batch_id",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start", "TIMESTAMP", start),
                bigquery.ScalarQueryParameter("end", "TIMESTAMP", start + dt.timedelta(days=1)),
            ]
        ),
        timeout=QUERY_TIMEOUT_SECONDS,
    )
    in_bq = {r["batch_id"]: r["n"] for r in job.result(timeout=QUERY_TIMEOUT_SECONDS)}
    result = compare(in_gcs, in_bq)
    print(f"{day}: " + ", ".join(f"{k} {len(v)}" for k, v in result.items()))
    for kind, batches in result.items():
        if kind != "equal" and batches:
            print(f"🔴 {kind}: {', '.join(batches[:20])}{' ...' if len(batches) > 20 else ''}")
    code = verdict(result)
    print({0: "✅ every batch equal", 1: "🔴 batches differ", 3: "⚪ no batch to compare"}[code])
    return code


def self_test() -> int:
    gcs = {"20261019T090000-r": 3, "20261019T090100-r": 2}
    control = compare(gcs, {"20261019T090000-r": 3, "20261019T090100-r": 2})
    checks = {
        "batch id from an object name": batch_id_of(
            "vps_stream/dt=2026-10-19/batch=090000-085500.parquet"
        )
        == "20261019T090000-085500"
        and batch_id_of("vps_stream/dt=2026-10-19/batch=090000-x.parquet.stored") is None,
        "control: equal everywhere passes": control["equal"] == sorted(gcs)
        and verdict(control) == 0,
        "planted: a batch never loaded": compare(gcs, {"20261019T090000-r": 3})[
            "missing_in_bigquery"
        ]
        == ["20261019T090100-r"],
        "planted: a batch loaded twice (unequal count)": compare(
            gcs, {"20261019T090000-r": 6, "20261019T090100-r": 2}
        )["unequal"]
        == ["20261019T090000-r"],
        "planted: rows in BigQuery without an object": compare(
            gcs, {**{k: v for k, v in gcs.items()}, "20261019T090200-r": 1}
        )["missing_in_gcs"]
        == ["20261019T090200-r"],
        "planted: an object without its count fails": verdict(compare({"a": None}, {"a": 1})) == 1,
        "nothing on either side is not a pass": verdict(compare({}, {})) == 3,
        "an unknown argument is rejected with exit 2": subprocess.run(  # noqa: S603
            [sys.executable, __file__, "--bogus"], capture_output=True, timeout=120, check=False
        ).returncode
        == 2,
    }
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date", type=dt.date.fromisoformat, help="session date, YYYY-MM-DD")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.date:
        parser.error("--date is required")
    from google.api_core.exceptions import GoogleAPIError
    from google.auth.exceptions import GoogleAuthError

    try:
        return run(args.date)
    except (FileNotFoundError, KeyError, GoogleAPIError, GoogleAuthError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
