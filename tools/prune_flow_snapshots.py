"""Remove flow snapshots older than the newest one from raw (dry run by default).

v1 rewrites its flow files whole every day, so each reload adds a full snapshot (~1 GB for
foreign flow) and staging reads only the newest. Raw is otherwise an append-only log; this
is the one deliberate exception, for the flow tables only (R3 plan, decision 2), and it never
touches the newest snapshot of a table or a table with a single snapshot.

Runs as sa-loader through impersonation. Exit codes: 0 = done (or dry run printed) ·
1 = self-test failed · 2 = cannot run.

Usage:
    python tools/prune_flow_snapshots.py            # dry run: what would go
    python tools/prune_flow_snapshots.py --apply
    python tools/prune_flow_snapshots.py --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys

from vnmarket.common.config import load_config, load_env, utf8_stdio


def to_drop(snapshots: list[tuple[str, dt.datetime, int]]) -> list[str]:
    """Hashes of every snapshot but the newest (by `_loaded_at`); [] for one or none."""
    if len(snapshots) < 2:
        return []
    newest = max(snapshots, key=lambda s: s[1])
    return [digest for digest, _, _ in snapshots if digest != newest[0]]


def run(apply: bool) -> int:
    from google.cloud import bigquery

    from vnmarket.common.gcp import impersonated

    cfg, env = load_config("el")["v1_history"], load_env()
    timeout = load_config("el")["reconcile_v1"]["query_timeout_seconds"]
    project = env["gcp"]["project_id"]
    client = bigquery.Client(
        project=project,
        credentials=impersonated(
            env["el"]["loader_service_account"],
            cfg["oauth_scope"],
            cfg["impersonation_token_seconds"],
        ),
    )
    for table in cfg["flows"]["files"].values():
        name = f"`{project}.{cfg['dataset']}.{table}`"
        rows = client.query(
            # Table names come from config/el.yml, not from input.
            f"select _source_sha256, max(_loaded_at) as loaded_at, count(*) as n from {name} "  # noqa: S608
            "group by 1",
            timeout=timeout,
        ).result(timeout=timeout)
        snaps = [(r["_source_sha256"], r["loaded_at"], r["n"]) for r in rows]
        drop = to_drop(snaps)
        rows_out = sum(n for d, _, n in snaps if d in drop)
        print(f"{table}: {len(snaps)} snapshots, would drop {len(drop)} ({rows_out:,} rows)")
        if apply and drop:
            job = client.query(
                f"delete from {name} where _source_sha256 in unnest(@drop)",  # noqa: S608
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[bigquery.ArrayQueryParameter("drop", "STRING", drop)]
                ),
                timeout=timeout,
            )
            job.result(timeout=timeout)
            print(f"  dropped {job.num_dml_affected_rows:,} rows")
    if not apply:
        print("Dry run: nothing deleted. --apply deletes.")
    return 0


def self_test() -> int:
    t0 = dt.datetime(2026, 10, 1, tzinfo=dt.UTC)
    later = t0 + dt.timedelta(days=30)
    checks = {
        "one snapshot: nothing to drop": to_drop([("a", t0, 5)]) == [],
        "no snapshot: nothing to drop": to_drop([]) == [],
        "the newest stays, the older go": to_drop([("old", t0, 5), ("new", later, 6)]) == ["old"],
        "order of the listing does not matter": to_drop([("new", later, 6), ("old", t0, 5)])
        == ["old"],
        "an unknown argument is rejected with exit 2": subprocess.run(  # noqa: S603
            [sys.executable, __file__, "--bogus"], capture_output=True, timeout=120
        ).returncode
        == 2,
    }
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="delete (default: dry run)")
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    try:
        return run(args.apply)
    except (FileNotFoundError, KeyError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
