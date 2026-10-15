"""Discover every tracked script that declares `--self-test` and run it; exit codes decide.

A script is discovered when its code (not a comment or a docstring) calls
`add_argument("--self-test", ...)`; discovery parses the source with `ast`.
Only files tracked by git are searched, so virtual environments and build
output never count. Finding nothing is a failure, not a pass: an empty run
proves nothing. A tracked file that does not parse is a failure too, never a
silent "has no self-test".

Exit codes: 0 = every self-test passed · 1 = a self-test failed or timed out,
a file did not parse, or none was found · 2 = usage or git error.

Usage:
    python tools/run_self_tests.py [--root PATH]
    python tools/run_self_tests.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from vnmarket.common.process import kill_tree

FLAG = "--self-test"
GIT_TIMEOUT_SECONDS = 60
SCRIPT_TIMEOUT_SECONDS = 120  # per script; the CI job's limit is the outer bound


def declares_self_test(source: str) -> bool:
    """Raise SyntaxError for a file that does not parse."""
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and any(isinstance(a, ast.Constant) and a.value == FLAG for a in node.args)
        ):
            return True
    return False


def tracked_python_files(root: Path) -> list[Path]:
    listing = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(root), "ls-files", "-z", "--", "*.py"],  # noqa: S607 - git from PATH
        capture_output=True,
        check=True,
        timeout=GIT_TIMEOUT_SECONDS,
    ).stdout.decode("utf-8")
    return sorted(root / name for name in listing.split("\0") if name)


def discover(root: Path) -> tuple[list[Path], list[Path]]:
    """Return (scripts declaring the flag, tracked files that do not parse)."""
    found, unparsable = [], []
    for path in tracked_python_files(root):
        try:
            if declares_self_test(path.read_text(encoding="utf-8")):
                found.append(path)
        except (SyntaxError, UnicodeDecodeError):
            unparsable.append(path)
    return found, unparsable


def run(script: Path, root: Path, timeout: float) -> int | None:
    """Return the exit code; None when the script timed out and its tree was killed."""
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell; scripts are this repo's own
        [sys.executable, str(script), FLAG],
        cwd=root,
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process)
        return None


def run_all(root: Path, timeout: float = SCRIPT_TIMEOUT_SECONDS) -> int:
    try:
        scripts, unparsable = discover(root)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"⚪ not run: git failed on {root}: {exc}", file=sys.stderr)
        return 2
    for path in unparsable:
        print(f"🔴 {path.relative_to(root)} does not parse; its self-test cannot be found")
    if not scripts:
        print(f"🔴 no tracked script declares {FLAG} under {root}")
        return 1
    results = []
    for script in scripts:
        print(f"--- {script.relative_to(root)} {FLAG}", flush=True)
        results.append((script, run(script, root, timeout)))
    print()
    for script, code in results:
        symbol, status = (
            ("🔴", "timed out") if code is None else ("✅" if code == 0 else "🔴", f"exit {code}")
        )
        print(f"{symbol} {script.relative_to(root)} ({status})")
    failed = sum(code != 0 for _, code in results)
    print(f"{len(results) - failed}/{len(results)} self-tests passed")
    return 1 if failed or unparsable else 0


def self_test() -> int:
    """Known answers on planted repositories; each fault turns exactly its own case red."""
    passing = (
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        'p.add_argument("--self-test", action="store_true")\n'
        "p.parse_args()\n"
        "sys.exit(0)\n"
    )
    failing = passing.replace("sys.exit(0)", "sys.exit(1)")
    hanging = passing.replace("sys.exit(0)", "import time\ntime.sleep(60)\n")
    # Mentions the flag only in a docstring and a comment, and fails if run.
    decoy = (
        '"""Usage: tool.py --self-test"""\n# add_argument("--self-test")\nimport sys\nsys.exit(1)\n'
    )

    def make_repo(root: Path, files: dict[str, str]) -> Path:
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=60)  # noqa: S603,S607
        files = {
            ".gitignore": ".venv/\n",
            "pass.py": passing,
            "decoy.py": decoy,
            ".venv/vendored.py": failing,
            **files,
        }
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, timeout=60)  # noqa: S603,S607
        return root

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        control = make_repo(t / "control", {})
        (control / "untracked.py").write_text(failing, encoding="utf-8")  # never added to git
        empty = make_repo(t / "empty", {"pass.py": "x = 1\n"})
        checks = {
            "discovery finds only tracked, real declarations": (
                [p.name for p in discover(control)[0]] == ["pass.py"]
            ),
            "control: all passing self-tests exit 0": run_all(control) == 0,
            "a planted failing self-test exits 1": (
                run_all(make_repo(t / "failing", {"fail.py": failing})) == 1
            ),
            "a planted unparsable file exits 1": (
                run_all(make_repo(t / "broken", {"broken.py": "def (:\n"})) == 1
            ),
            "a planted hanging self-test times out and exits 1": (
                run_all(make_repo(t / "hanging", {"hang.py": hanging}), timeout=3) == 1
            ),
            "finding no self-test exits 1": run_all(empty) == 1,
            "an unknown argument is rejected with exit 2": subprocess.run(  # noqa: S603
                [sys.executable, __file__, "--bogus"], capture_output=True, timeout=60
            ).returncode
            == 2,
        }
    print()
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path("."), help="repository root (default: .)")
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    return self_test() if args.self_test else run_all(args.root.resolve())


if __name__ == "__main__":
    sys.exit(main())
