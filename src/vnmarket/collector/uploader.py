"""Move the collector's spool to the raw bucket and into BigQuery, verified (spec S1, S2).

Each finished batch (`*.parquet`; the collector's `*.tmp` files are ignored) goes through
two steps, and the local file is deleted only after both:

1. **Archive.** Uploaded to `gs://<raw bucket>/<prefix>/dt=.../batch=...parquet` only if no
   object has that name yet (`if_generation_match=0`), with its message count as object
   metadata (`messages`). The size and CRC32C the bucket reports for the stored object (in
   the upload's response) must equal the local file's (engineering rule: do not trust the
   transfer); then a marker `<batch>.parquet.stored` records it. When the name is already
   taken, the object is read back: the same bytes count as stored; different content, or an
   object the collector may not read (it can create objects, not read them), moves the file
   to `<spool>/../conflict/` - never overwritten, never deleted.
2. **Load.** A BigQuery load job appends the same local file - the bytes just verified - to
   the stream table (ADR-0031: the collector's account cannot read the bucket). The job id is
   derived from the batch and an attempt number kept in the marker: a load retried after a
   timeout finds its job instead of appending twice, and a new attempt is made only after
   the previous job is known to have failed. The job's `output_rows` must equal the file's
   rows; otherwise the file moves to `conflict/` (rows were appended: a person decides).

One JSON line per finished batch (`batch_uploaded`, with messages and loaded rows), and one
point of the custom metric `upload.metric_type` (at most one per `metric_min_seconds`): the
stale-feed alert of S1.4 watches that metric, so it works on any host without a log agent
(ADR-0032). Time limits: every upload, metadata read, job wait and metric write.

Credentials: none in code (D12). On the VM, the attached service account; elsewhere the
owner's application-default credentials, impersonating `collector.service_account` from
config/env/prod.yml when it is set.

Exit codes: 0 = the spool is empty at the end · 1 = batches left or in conflict ·
2 = cannot run (config, credentials).

Usage:
    python -m vnmarket.collector.uploader --once
    python -m vnmarket.collector.uploader --until 15:05     # poll, then drain
    python -m vnmarket.collector.uploader --self-test
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq

from vnmarket.collector.stream_collector import log_event
from vnmarket.common.config import REPO_ROOT, load_config, load_env, utf8_stdio

SCOPE = "https://www.googleapis.com/auth/cloud-platform"  # storage and BigQuery
TOKEN_SECONDS = 3600
MARKER = ".stored"


class AlreadyExists(Exception):
    """An object with this name, or a job with this id, already exists."""


class Bucket(Protocol):
    def upload(self, path: Path, name: str, messages: int) -> tuple[int, str]: ...  # stored
    def stat(self, name: str) -> tuple[int, str] | None: ...  # (size, base64 CRC32C)


class Warehouse(Protocol):
    def load(self, path: Path, job_id: str) -> int: ...  # rows appended
    def job_rows(self, job_id: str) -> int | None: ...  # rows if it succeeded, None if failed


class MetricSink(Protocol):
    def record(self, messages: int) -> None: ...


class GcpMetric:
    """One point of a custom gauge per call (S1.4): the stale-feed alert watches it."""

    def __init__(self, project: str, metric_type: str, timeout: float, credentials: Any = None):
        from google.cloud import monitoring_v3

        self.monitoring = monitoring_v3
        self.client = monitoring_v3.MetricServiceClient(credentials=credentials)
        self.project, self.metric_type, self.timeout = project, metric_type, timeout

    def record(self, messages: int) -> None:
        m = self.monitoring
        series = m.TimeSeries()
        series.metric.type = self.metric_type
        series.resource.type = "global"
        series.resource.labels["project_id"] = self.project
        now = time.time()
        interval = m.TimeInterval(
            {"end_time": {"seconds": int(now), "nanos": int((now % 1) * 1e9)}}
        )
        series.points = [m.Point({"interval": interval, "value": {"int64_value": messages}})]
        self.client.create_time_series(
            name=f"projects/{self.project}", time_series=[series], timeout=self.timeout
        )


class Heartbeat:
    """Records loaded batches to the metric, at most one point per `min_seconds` (Cloud
    Monitoring refuses points written faster than one every 5 s per series). A failed write
    is logged and never holds a batch back: the alert is about batches, not about itself."""

    def __init__(self, sink: MetricSink, min_seconds: float, clock=time.monotonic) -> None:
        self.sink, self.min_seconds, self.clock = sink, min_seconds, clock
        self.last: float | None = None

    def beat(self, messages: int) -> None:
        now = self.clock()
        if self.last is not None and now - self.last < self.min_seconds:
            return
        self.last = now
        try:
            self.sink.record(messages)
        except Exception as exc:  # noqa: BLE001 - the batch is done either way
            log_event("metric_failed", error=type(exc).__name__)


def local_stat(path: Path) -> tuple[int, str]:
    import google_crc32c

    data = path.read_bytes()
    digest = google_crc32c.Checksum(data).digest()
    return len(data), base64.b64encode(digest).decode("ascii")


class GcsBucket:
    def __init__(self, bucket: str, timeout: float, credentials: Any = None, project=None):
        from google.cloud import storage

        self.bucket = storage.Client(project=project, credentials=credentials).bucket(bucket)
        self.timeout = timeout

    def upload(self, path: Path, name: str, messages: int) -> tuple[int, str]:
        from google.api_core.exceptions import PreconditionFailed

        blob = self.bucket.blob(name)
        blob.metadata = {"messages": str(messages)}
        try:
            blob.upload_from_filename(
                str(path), if_generation_match=0, timeout=self.timeout, checksum="crc32c"
            )
        except PreconditionFailed as exc:
            raise AlreadyExists(name) from exc
        return blob.size, blob.crc32c  # from the upload's response: no read permission needed

    def stat(self, name: str) -> tuple[int, str] | None:
        blob = self.bucket.get_blob(name, timeout=self.timeout)
        return (blob.size, blob.crc32c) if blob else None


class BigQueryTable:
    def __init__(self, table: str, timeout: float, credentials: Any = None, project=None):
        from google.cloud import bigquery

        self.client = bigquery.Client(project=project, credentials=credentials)
        self.table, self.timeout = table, timeout
        self.config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

    def load(self, path: Path, job_id: str) -> int:
        from google.api_core.exceptions import Conflict

        try:
            with path.open("rb") as handle:
                job = self.client.load_table_from_file(
                    handle,
                    self.table,
                    job_id=job_id,
                    job_config=self.config,
                    timeout=self.timeout,
                )
        except Conflict as exc:
            raise AlreadyExists(job_id) from exc
        job.result(timeout=self.timeout)  # raises if the job failed
        return job.output_rows

    def job_rows(self, job_id: str) -> int | None:
        job = self.client.get_job(job_id, timeout=self.timeout)
        try:
            job.result(timeout=self.timeout)
        except Exception:  # noqa: BLE001 - a failed job; a timeout raises from get_job's wait
            if job.done() and job.error_result:
                return None
            raise
        return job.output_rows


def pending(spool: Path) -> list[Path]:
    return sorted(spool.rglob("*.parquet")) if spool.exists() else []


def job_id_for(spool: Path, path: Path, attempt: int) -> str:
    """`vnm_load_<date>_<window>-<run>_<attempt>`: letters, digits, dashes, underscores."""
    rel = path.relative_to(spool).as_posix().removesuffix(".parquet")
    return f"vnm_load_{re.sub(r'[^A-Za-z0-9_-]+', '_', rel)}_{attempt}"


def move_to_conflict(spool: Path, path: Path, event: str) -> None:
    target = spool.parent / "conflict" / path.relative_to(spool)
    target.parent.mkdir(parents=True, exist_ok=True)
    path.replace(target)
    marker = path.with_name(path.name + MARKER)
    if marker.exists():
        marker.replace(target.with_name(target.name + MARKER))
    log_event(event, batch=path.name)


def archive(spool: Path, path: Path, bucket: Bucket, prefix: str, messages: int) -> str:
    """'stored', 'failed' (retry next pass) or 'conflict' (moved aside)."""
    name = f"{prefix}/{path.relative_to(spool).as_posix()}"
    mine = local_stat(path)
    existed = False
    try:
        theirs = bucket.upload(path, name, messages)
    except AlreadyExists:
        existed = True
    except Exception as exc:  # noqa: BLE001 - kept in the spool, retried next pass
        log_event("upload_failed", batch=path.name, error=type(exc).__name__)
        return "failed"
    if existed:
        try:
            theirs = bucket.stat(name)
        except Exception as exc:  # noqa: BLE001 - cannot compare: a conflict to review
            log_event("verify_failed", batch=path.name, error=type(exc).__name__)
            theirs = None
    if theirs == mine:
        return "stored"
    if existed:
        move_to_conflict(spool, path, "batch_conflict")
        return "conflict"
    log_event("verify_mismatch", batch=path.name)  # the next pass finds a taken name
    return "failed"


def load(spool: Path, path: Path, warehouse: Warehouse, state: dict) -> int | None:
    """Rows loaded, exactly once; None when this pass could not finish (retried next pass)."""
    job_id = job_id_for(spool, path, state["attempt"])
    try:
        return warehouse.load(path, job_id)
    except AlreadyExists:
        pass  # an earlier pass created this job: find out how it ended
    except Exception as exc:  # noqa: BLE001 - the job may exist: the next pass asks for it
        log_event("load_failed", batch=path.name, error=type(exc).__name__)
        return None
    try:
        rows = warehouse.job_rows(job_id)
    except Exception as exc:  # noqa: BLE001 - still running or unreachable: ask again later
        log_event("load_unknown", batch=path.name, error=type(exc).__name__)
        return None
    if rows is None:  # that attempt failed and appended nothing: try anew under a new id
        state["attempt"] += 1
        log_event("load_retry", batch=path.name, attempt=state["attempt"])
        return load(spool, path, warehouse, state)
    return rows


def upload_pass(
    spool: Path,
    bucket: Bucket,
    prefix: str,
    warehouse: Warehouse,
    heartbeat: Heartbeat | None = None,
) -> dict[str, int]:
    """One pass over the spool; returns counts by outcome."""
    counts = {"uploaded": 0, "failed": 0, "conflict": 0}
    for path in pending(spool):
        messages = pq.read_metadata(path).num_rows
        marker = path.with_name(path.name + MARKER)
        state = json.loads(marker.read_text("utf-8")) if marker.exists() else None
        if state is None:
            outcome = archive(spool, path, bucket, prefix, messages)
            if outcome != "stored":
                counts[outcome] += 1
                continue
            state = {"attempt": 0}
            marker.write_text(json.dumps(state), "utf-8")
        rows = load(spool, path, warehouse, state)
        marker.write_text(json.dumps(state), "utf-8")
        if rows is None:
            counts["failed"] += 1
        elif rows != messages:
            move_to_conflict(spool, path, "load_mismatch")
            counts["conflict"] += 1
        else:
            path.unlink()
            marker.unlink()
            log_event("batch_uploaded", batch=path.name, messages=messages, loaded_rows=rows)
            counts["uploaded"] += 1
            if heartbeat:
                heartbeat.beat(messages)
    return counts


def run(
    spool: Path,
    bucket: Bucket,
    prefix: str,
    warehouse: Warehouse,
    stop_at: float | None,
    cfg: dict,
    heartbeat: Heartbeat | None = None,
) -> int:
    """Poll until `stop_at` (epoch seconds), then drain; `None` means a single pass."""
    totals = {"uploaded": 0, "failed": 0, "conflict": 0}

    def one() -> None:
        for k, v in upload_pass(spool, bucket, prefix, warehouse, heartbeat).items():
            totals[k] += v

    one()
    if stop_at is not None:
        while time.time() < stop_at:
            time.sleep(cfg["poll_seconds"])
            one()
        drain_until = time.time() + cfg["drain_minutes"] * 60
        while pending(spool) and time.time() < drain_until:
            time.sleep(cfg["poll_seconds"])
            one()
    left = len(pending(spool))
    log_event("upload_finished", **totals, left=left)
    return 0 if left == 0 and totals["conflict"] == 0 else 1


# --- self-test --------------------------------------------------------------------------


class FakeBucket:
    """In-memory bucket with planted failures."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict] = {}
        self.fail_uploads = 0  # the next N uploads raise
        self.corrupt_next = False  # the next upload stores different bytes
        self.uploads = 0
        self.readable = True  # False: like the collector's account, which cannot read

    def upload(self, path: Path, name: str, messages: int) -> tuple[int, str]:
        self.uploads += 1
        if self.fail_uploads:
            self.fail_uploads -= 1
            raise TimeoutError("planted")
        if name in self.objects:
            raise AlreadyExists(name)
        data = path.read_bytes()
        if self.corrupt_next:
            self.corrupt_next, data = False, data[:-1] + bytes([data[-1] ^ 1])
        self.objects[name] = data
        self.metadata[name] = {"messages": str(messages)}
        return self._stat(name)

    def stat(self, name: str) -> tuple[int, str] | None:
        if not self.readable:
            raise PermissionError("planted: storage.objects.get denied")
        return self._stat(name)

    def _stat(self, name: str) -> tuple[int, str] | None:
        import google_crc32c

        data = self.objects.get(name)
        if data is None:
            return None
        return len(data), base64.b64encode(google_crc32c.Checksum(data).digest()).decode()


class FakeTable:
    """In-memory table and job registry with planted failures."""

    def __init__(self) -> None:
        self.rows: list[str] = []  # payloads appended
        self.jobs: dict[str, int | None] = {}  # job id -> rows, None = failed
        self.fail_next = False  # the job is created and fails, appending nothing
        self.timeout_next = False  # the job is created and succeeds; the wait times out
        self.short_next = False  # the job reports one row fewer than it appended

    def load(self, path: Path, job_id: str) -> int:
        if job_id in self.jobs:
            raise AlreadyExists(job_id)
        if self.fail_next:
            self.fail_next, self.jobs[job_id] = False, None
            raise RuntimeError("planted job failure")
        payloads = pq.read_table(path).column("payload").to_pylist()
        self.rows += payloads
        reported = len(payloads) - (1 if self.short_next else 0)
        self.short_next = False
        self.jobs[job_id] = reported
        if self.timeout_next:
            self.timeout_next = False
            raise TimeoutError("planted wait timeout")
        return reported

    def job_rows(self, job_id: str) -> int | None:
        return self.jobs[job_id]


def self_test() -> int:
    import subprocess
    import tempfile

    from vnmarket.collector.stream_collector import Batcher

    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory() as tmp:
        spool = Path(tmp) / "spool"
        t0 = dt.datetime(2026, 10, 19, 2, 0, tzinfo=dt.UTC).timestamp()
        now = [t0]
        batcher = Batcher(spool, 60, tz, "run", clock=lambda: now[0])

        def batch(minute: int, *payloads: str) -> None:
            now[0] = t0 + minute * 60 + 1
            for p in payloads:
                batcher.add(p)
            batcher.close()

        def one(b, t):
            return upload_pass(spool, b, "vps_stream", t)

        for minute in range(3):
            batch(minute, f"m{minute}a", f"m{minute}b")
        (spool / "dt=2026-10-19" / "batch=090300-run.parquet.tmp").write_bytes(b"partial")
        bucket, table = FakeBucket(), FakeTable()

        bucket.fail_uploads = 1  # planted: the first upload times out
        first = one(bucket, table)
        checks["control: archived, loaded with the same row count, then removed"] = (
            first == {"uploaded": 2, "failed": 1, "conflict": 0}
            and len(table.rows) == 4
            and bucket.metadata["vps_stream/dt=2026-10-19/batch=090100-run.parquet"]
            == {"messages": "2"}
        )
        second = one(bucket, table)
        checks["a failed upload stays in the spool; the next pass archives and loads it once"] = (
            second["uploaded"] == 1
            and not pending(spool)
            and sorted(table.rows) == sorted(f"m{m}{x}" for m in range(3) for x in "ab")
        )
        checks["a partial file is never uploaded"] = (
            spool / "dt=2026-10-19" / "batch=090300-run.parquet.tmp"
        ).exists()

        # Archived, then the load job fails: only the load is retried, under a new attempt.
        batch(4, "m4")
        uploads_before = bucket.uploads
        table.fail_next = True
        failed = one(bucket, table)
        retried = one(bucket, table)
        checks["a failed load keeps the file; the retry loads it alone, under a new job id"] = (
            failed["failed"] == 1
            and retried["uploaded"] == 1
            and bucket.uploads == uploads_before + 1
            and table.rows.count("m4") == 1
            and any(j.endswith("_1") for j in table.jobs)
        )

        # The job succeeded but the wait timed out: the next pass finds it, no second append.
        batch(5, "m5")
        table.timeout_next = True
        one(bucket, table)
        one(bucket, table)
        checks["a load whose wait timed out is found again, never appended twice"] = (
            table.rows.count("m5") == 1 and not pending(spool)
        )

        # The job reports fewer rows than the file holds: a conflict for a person.
        batch(6, "m6a", "m6b")
        table.short_next = True
        short = one(bucket, table)
        checks["a row count that differs moves the file to conflict, with its marker"] = (
            short["conflict"] == 1
            and any((spool.parent / "conflict").rglob("*.parquet"))
            and any((spool.parent / "conflict").rglob("*" + MARKER))
        )

        # Archive conflicts: a different object, or one the account cannot read.
        batch(7, "m7")
        [clash] = pending(spool)
        clash_name = f"vps_stream/{clash.relative_to(spool).as_posix()}"
        bucket.objects[clash_name] = b"someone else's"
        bucket.readable = False
        hidden = one(bucket, table)
        bucket.readable = True
        checks["a taken name it cannot read or match: conflict, not overwritten, not loaded"] = (
            hidden["conflict"] == 1
            and bucket.objects[clash_name] == b"someone else's"
            and "m7" not in table.rows
        )

        # Uploaded, then stopped before the marker: the same bytes count as stored.
        batch(8, "m8")
        [again] = pending(spool)
        bucket.objects[f"vps_stream/{again.relative_to(spool).as_posix()}"] = again.read_bytes()
        checks["an object already there with the same bytes counts as stored"] = one(
            bucket, table
        ) == {"uploaded": 1, "failed": 0, "conflict": 0}

        # A transfer that changes the bytes: neither trusted nor loaded.
        batch(9, "m9")
        bucket.corrupt_next = True
        corrupt = one(bucket, table)
        checks["a transfer that changed the bytes: the file stays, nothing loaded"] = (
            corrupt["failed"] == 1 and len(pending(spool)) == 1 and "m9" not in table.rows
        )
        checks["run: exit 1 while anything is left or in conflict"] = (
            run(spool, bucket, "vps_stream", table, None, {}) == 1
        )

        # The metric: one point per loaded batch, spaced; never for a failed batch; a failing
        # sink holds nothing back.
        class Sink:
            def __init__(self, fail: bool = False) -> None:
                self.points: list[int] = []
                self.fail = fail

            def record(self, messages: int) -> None:
                if self.fail:
                    raise TimeoutError("planted")
                self.points.append(messages)

        clock = [0.0]
        sink = Sink()
        beat = Heartbeat(sink, 10, clock=lambda: clock[0])
        batch(20, "a1", "a2")
        upload_pass(spool, bucket, "vps_stream", table, beat)
        clock[0] = 5.0  # too soon after the last point
        batch(21, "b1")
        upload_pass(spool, bucket, "vps_stream", table, beat)
        clock[0] = 16.0
        batch(22, "c1", "c2", "c3")
        table.fail_next = True  # the load fails on this pass: no point for it
        upload_pass(spool, bucket, "vps_stream", table, beat)
        upload_pass(spool, bucket, "vps_stream", table, beat)  # loaded now: a point
        checks["metric: one point per loaded batch, spaced, none for a failed load"] = (
            sink.points == [2, 3]
        )
        broken = Heartbeat(Sink(fail=True), 10, clock=lambda: clock[0])
        batch(23, "d1")
        checks["metric: a failing write never holds a batch back"] = upload_pass(
            spool, bucket, "vps_stream", table, broken
        )["uploaded"] >= 1 and not [p for p in pending(spool) if "091300" in p.name]

        checks["job ids: only letters, digits, dashes and underscores"] = (
            re.fullmatch(
                r"[A-Za-z0-9_-]+",
                job_id_for(spool, spool / "dt=2026-10-19/batch=090000-x.parquet", 0),
            )
            is not None
        )

    checks["an unknown argument is rejected with exit 2"] = (
        subprocess.run(  # noqa: S603 - this module, fixed arguments
            [sys.executable, "-m", "vnmarket.collector.uploader", "--bogus"],
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="one pass, then exit")
    mode.add_argument("--until", help="poll until this Vietnam time, HH:MM, then drain")
    mode.add_argument("--self-test", action="store_true")
    parser.add_argument("--spool", type=Path, help="local spool directory (default: config)")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not (args.once or args.until):
        parser.error("--once or --until is required")
    cfg = load_config("collector")
    up = cfg["upload"]
    try:
        env = load_env()
        project = env["gcp"]["project_id"]
        credentials = None
        account = (env.get("collector") or {}).get("service_account")
        if account:
            from vnmarket.common.gcp import impersonated

            credentials = impersonated(account, SCOPE, TOKEN_SECONDS)
        bucket = GcsBucket(
            env["gcp"]["raw_bucket"], up["call_timeout_seconds"], credentials, project
        )
        table = BigQueryTable(
            f"{project}.{up['load_table']}", up["call_timeout_seconds"], credentials, project
        )
        heartbeat = Heartbeat(
            GcpMetric(project, up["metric_type"], up["call_timeout_seconds"], credentials),
            up["metric_min_seconds"],
        )
    except (FileNotFoundError, KeyError) as exc:
        print(f"⚪ not run: {exc}", file=sys.stderr)
        return 2
    stop_at = None
    if args.until:
        tz = ZoneInfo(cfg["timezone"])
        hour, minute = map(int, args.until.split(":"))
        stop_at = dt.datetime.now(tz).replace(hour=hour, minute=minute, second=0).timestamp()
    spool = args.spool or REPO_ROOT / cfg["spool_dir"]
    return run(spool, bucket, up["prefix"], table, stop_at, up, heartbeat)


if __name__ == "__main__":
    sys.exit(main())
