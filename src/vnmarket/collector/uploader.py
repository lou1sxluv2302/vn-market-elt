"""Move the collector's spool to the raw bucket, verified (spec S1).

Each finished batch (`*.parquet`; the collector's `*.tmp` files are ignored) is uploaded to
`gs://<raw bucket>/<prefix>/dt=.../batch=...parquet` only if no object has that name yet
(`if_generation_match=0`); the size and CRC32C the bucket reports for the stored object
(in the upload's response) are compared with the local file. Only a match deletes the local
file (engineering rule: do not trust the transfer). A failed upload stays in the spool and
is tried again on the next pass. When the name is already taken, the existing object is
read back: the same size and checksum (an earlier pass uploaded it, then stopped before
deleting) counts as uploaded; different content, or an object the collector may not read
(it can create objects, not read them), is moved to `<spool>/../conflict/` and reported -
never overwritten, never deleted.

One JSON line per uploaded batch (`batch_uploaded`, with its message count): the alert of
step S1.4 counts these lines. Time limits: every upload and every metadata read.

Credentials: none in code (D12). On the VM, the attached service account; elsewhere the
owner's application-default credentials, impersonating `collector_service_account` from
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
import sys
import time
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq

from vnmarket.collector.stream_collector import log_event
from vnmarket.common.config import REPO_ROOT, load_config, load_env, utf8_stdio

STORAGE_SCOPE = "https://www.googleapis.com/auth/devstorage.read_write"
TOKEN_SECONDS = 3600


class AlreadyExists(Exception):
    """An object with this name is already in the bucket."""


class Bucket(Protocol):
    def upload(self, path: Path, name: str) -> tuple[int, str]: ...  # as stored
    def stat(self, name: str) -> tuple[int, str] | None: ...  # (size, base64 CRC32C)


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

    def upload(self, path: Path, name: str) -> tuple[int, str]:
        from google.api_core.exceptions import PreconditionFailed

        blob = self.bucket.blob(name)
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


def pending(spool: Path) -> list[Path]:
    return sorted(spool.rglob("*.parquet")) if spool.exists() else []


def upload_pass(spool: Path, bucket: Bucket, prefix: str) -> dict[str, int]:
    """One pass over the spool; returns counts by outcome."""
    counts = {"uploaded": 0, "failed": 0, "conflict": 0}
    for path in pending(spool):
        name = f"{prefix}/{path.relative_to(spool).as_posix()}"
        mine = local_stat(path)
        existed = False
        try:
            theirs = bucket.upload(path, name)
        except AlreadyExists:
            existed = True
        except Exception as exc:  # noqa: BLE001 - kept in the spool, retried next pass
            log_event("upload_failed", batch=path.name, error=type(exc).__name__)
            counts["failed"] += 1
            continue
        if existed:
            try:
                theirs = bucket.stat(name)
            except Exception as exc:  # noqa: BLE001 - cannot compare: a conflict to review
                log_event("verify_failed", batch=path.name, error=type(exc).__name__)
                theirs = None
        if theirs == mine:
            messages = pq.read_metadata(path).num_rows
            path.unlink()
            log_event("batch_uploaded", batch=path.name, messages=messages, bytes=mine[0])
            counts["uploaded"] += 1
        elif existed:
            target = spool.parent / "conflict" / path.relative_to(spool)
            target.parent.mkdir(parents=True, exist_ok=True)
            path.replace(target)
            log_event("batch_conflict", batch=path.name)
            counts["conflict"] += 1
        else:  # uploaded but read back different: keep it; the next pass sees a conflict
            log_event("verify_mismatch", batch=path.name)
            counts["failed"] += 1
    return counts


def run(spool: Path, bucket: Bucket, prefix: str, stop_at: float | None, cfg: dict) -> int:
    """Poll until `stop_at` (epoch seconds), then drain; `None` means a single pass."""
    totals = {"uploaded": 0, "failed": 0, "conflict": 0}

    def one() -> None:
        for k, v in upload_pass(spool, bucket, prefix).items():
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
        self.fail_uploads = 0  # the next N uploads raise
        self.corrupt_next = False  # the next upload stores different bytes
        self.uploads = 0
        self.readable = True  # False: like the collector's account, which cannot read

    def upload(self, path: Path, name: str) -> tuple[int, str]:
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
        return self.stat(name)

    def stat(self, name: str) -> tuple[int, str] | None:
        import google_crc32c

        if not self.readable:
            raise PermissionError("planted: storage.objects.get denied")
        data = self.objects.get(name)
        if data is None:
            return None
        return len(data), base64.b64encode(google_crc32c.Checksum(data).digest()).decode()


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
        for minute in range(3):
            now[0] = t0 + minute * 60 + 1
            batcher.add(f"m{minute}")
        batcher.close()
        (spool / "dt=2026-10-19" / "batch=090300-run.parquet.tmp").write_bytes(b"partial")
        bucket = FakeBucket()

        bucket.fail_uploads = 1  # planted: the first upload times out
        first = upload_pass(spool, bucket, "vps_stream")
        checks["a failed upload stays in the spool; the others are verified and removed"] = (
            first == {"uploaded": 2, "failed": 1, "conflict": 0} and len(pending(spool)) == 1
        )
        second = upload_pass(spool, bucket, "vps_stream")
        checks["the next pass uploads it, once"] = (
            second["uploaded"] == 1
            and not pending(spool)
            and sorted(bucket.objects)
            == [f"vps_stream/dt=2026-10-19/batch=09{m}00-run.parquet" for m in ("00", "01", "02")]
        )
        checks["a partial file is never uploaded"] = (
            spool / "dt=2026-10-19" / "batch=090300-run.parquet.tmp"
        ).exists()

        # Uploaded, then stopped before deleting: the same content counts as uploaded.
        now[0] = t0 + 4 * 60 + 1
        batcher.add("m4")
        batcher.close()
        [again] = pending(spool)
        name = f"vps_stream/{again.relative_to(spool).as_posix()}"
        bucket.objects[name] = again.read_bytes()
        checks["an object already there with the same bytes counts as uploaded"] = upload_pass(
            spool, bucket, "vps_stream"
        ) == {"uploaded": 1, "failed": 0, "conflict": 0}

        # Different content under the same name: moved aside, never overwritten.
        now[0] = t0 + 5 * 60 + 1
        batcher.add("m5")
        batcher.close()
        [clash] = pending(spool)
        clash_name = f"vps_stream/{clash.relative_to(spool).as_posix()}"
        bucket.objects[clash_name] = b"someone else's"
        result = upload_pass(spool, bucket, "vps_stream")
        checks["a different object under the same name: conflict, kept, not overwritten"] = (
            result["conflict"] == 1
            and bucket.objects[clash_name] == b"someone else's"
            and any((spool.parent / "conflict").rglob("*.parquet"))
        )

        # The name is taken and the account cannot read it: a conflict, never deleted.
        now[0] = t0 + 7 * 60 + 1
        batcher.add("m7")
        batcher.close()
        [hidden] = [p for p in pending(spool) if "090700" in p.name]
        bucket.objects[f"vps_stream/{hidden.relative_to(spool).as_posix()}"] = b"unknown"
        bucket.readable = False
        hidden_result = upload_pass(spool, bucket, "vps_stream")
        bucket.readable = True
        checks["a taken name the account cannot read: conflict, the local file kept"] = (
            hidden_result["conflict"] == 1
            and not hidden.exists()
            and (spool.parent / "conflict" / hidden.relative_to(spool)).exists()
        )

        # A transfer that changes the bytes: not deleted locally.
        now[0] = t0 + 6 * 60 + 1
        batcher.add("m6")
        batcher.close()
        bucket.corrupt_next = True
        corrupt = upload_pass(spool, bucket, "vps_stream")
        checks["a transfer that changed the bytes is not trusted: the file stays"] = (
            corrupt["failed"] == 1 and len(pending(spool)) == 1
        )
        checks["run: exit 1 while anything is left or in conflict"] = (
            run(spool, bucket, "vps_stream", None, {}) == 1
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
    try:
        env = load_env()
        credentials = None
        account = env.get("collector", {}).get("service_account")
        if account:
            from vnmarket.common.gcp import impersonated

            credentials = impersonated(account, STORAGE_SCOPE, TOKEN_SECONDS)
        bucket = GcsBucket(
            env["gcp"]["raw_bucket"],
            cfg["upload"]["call_timeout_seconds"],
            credentials,
            env["gcp"]["project_id"],
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
    return run(spool, bucket, cfg["upload"]["prefix"], stop_at, cfg["upload"])


if __name__ == "__main__":
    sys.exit(main())
