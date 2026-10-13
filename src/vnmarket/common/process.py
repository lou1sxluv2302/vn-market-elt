"""Run a child process with a time limit that stops its whole tree (engineering-rules).

`subprocess.run(timeout=)` kills only the direct child; a grandchild holding the pipe open
keeps the wait going (v1 2026-08-14). `run_bounded` starts the child in its own process
group and, on timeout, kills the group (POSIX) or the tree (`taskkill /T`, Windows).

Usage:
    python -m vnmarket.common.process --self-test
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

KILL_TIMEOUT_SECONDS = 30  # taskkill itself; it returns in well under a second


class Timeout(Exception):
    """The child ran past its limit; its whole tree was killed."""


def kill_tree(process: subprocess.Popen) -> None:
    """Stop the process and everything it started."""
    if os.name == "nt":
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],  # noqa: S607 - Windows built-in
            capture_output=True,
            timeout=KILL_TIMEOUT_SECONDS,
        )
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def run_bounded(
    argv: list[str], timeout: float, *, cwd: Path | None = None, capture: bool = True
) -> subprocess.CompletedProcess:
    """Run `argv`; raise Timeout after killing its tree when it passes `timeout` seconds.
    With `capture`, stdout and stderr come back as one UTF-8 text."""
    process = subprocess.Popen(  # noqa: S603 - callers pass fixed argv, no shell
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        out, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        kill_tree(process)
        process.communicate()
        name = Path(argv[0]).name
        raise Timeout(f"{name} passed {timeout}s; its process tree was killed") from exc
    text = out.decode("utf-8", errors="replace") if out is not None else ""
    return subprocess.CompletedProcess(argv, process.returncode, text, None)


def self_test() -> int:
    """A child that starts a sleeping grandchild is stopped at the limit (planted hang); a
    quick child returns its output and exit code (control)."""
    grandchild = "import time; time.sleep(60)"
    parent = (
        "import subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]); "
        "print('started', flush=True); "
        "import time; time.sleep(60)"
    )
    started = time.monotonic()
    try:
        run_bounded([sys.executable, "-c", parent], timeout=3)
        hang_stopped = False
    except Timeout:
        hang_stopped = True
    elapsed = time.monotonic() - started
    quick = run_bounded([sys.executable, "-c", "print('ok'); raise SystemExit(3)"], timeout=60)
    checks = {
        "planted hang with a grandchild is stopped at the limit": hang_stopped and elapsed < 30,
        "control: a quick child returns its output": quick.stdout.strip() == "ok",
        "control: a quick child returns its exit code": quick.returncode == 3,
    }
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("nothing to do without --self-test")
    return self_test()


if __name__ == "__main__":
    sys.exit(main())
