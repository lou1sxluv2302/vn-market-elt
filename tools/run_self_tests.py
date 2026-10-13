"""Discover every script that declares `--self-test` and run it; exit codes decide.

A script is discovered when its code (not a comment or a docstring) calls
`add_argument("--self-test", ...)`; discovery parses the source with `ast`.
Finding nothing is a failure, not a pass: an empty run proves nothing.

Exit codes: 0 = every self-test passed · 1 = a self-test failed, timed out or
none was found.

Usage:
    python tools/run_self_tests.py [--root PATH]
    python tools/run_self_tests.py --self-test
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tempfile
from pathlib import Path

FLAG = "--self-test"
SCRIPT_TIMEOUT_SECONDS = 300
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dbt_packages", "target"}


def declares_self_test(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and any(isinstance(a, ast.Constant) and a.value == FLAG for a in node.args)
        ):
            return True
    return False


def discover(root: Path) -> list[Path]:
    found = []
    for path in sorted(root.rglob("*.py")):
        if SKIP_DIRS.intersection(path.relative_to(root).parts):
            continue
        if declares_self_test(path.read_text(encoding="utf-8", errors="replace")):
            found.append(path)
    return found


def run(script: Path, root: Path) -> tuple[str, int | None]:
    """Return (symbol, exit code); a timeout has no exit code."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell; scripts are this repo's own
            [sys.executable, str(script), FLAG],
            cwd=root, timeout=SCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return "🔴", None
    return ("✅" if result.returncode == 0 else "🔴"), result.returncode


def run_all(root: Path) -> int:
    scripts = discover(root)
    if not scripts:
        print(f"🔴 no script declares {FLAG} under {root}")
        return 1
    results = []
    for script in scripts:
        print(f"--- {script.relative_to(root)} {FLAG}", flush=True)
        results.append((script, *run(script, root)))
    print()
    for script, symbol, code in results:
        status = "timed out" if code is None else f"exit {code}"
        print(f"{symbol} {script.relative_to(root)} ({status})")
    failed = sum(symbol != "✅" for _, symbol, _ in results)
    print(f"{len(results) - failed}/{len(results)} self-tests passed")
    return 1 if failed else 0


def self_test() -> int:
    """Known answers on planted scripts: one passes, one fails, two must not be found."""
    passing = (
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        'p.add_argument("--self-test", action="store_true")\n'
        "p.parse_args()\n"
        "sys.exit(0)\n"
    )
    failing = passing.replace("sys.exit(0)", "sys.exit(1)")
    # Mentions the flag only in a docstring and a comment, and fails if run.
    decoy = (
        '"""Usage: tool.py --self-test"""\n'
        '# add_argument("--self-test")\n'
        "import sys\n"
        "sys.exit(1)\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        good, bad = Path(tmp) / "good", Path(tmp) / "bad"
        for root in (good, bad):
            root.mkdir()
            (root / "pass.py").write_text(passing, encoding="utf-8")
            (root / "decoy.py").write_text(decoy, encoding="utf-8")
            (root / ".venv").mkdir()
            (root / ".venv" / "vendored.py").write_text(failing, encoding="utf-8")
        (bad / "fail.py").write_text(failing, encoding="utf-8")
        empty = Path(tmp) / "empty"
        empty.mkdir()
        (empty / "decoy.py").write_text(decoy, encoding="utf-8")

        checks = {
            "discovery finds only real declarations": (
                [p.name for p in discover(good)] == ["pass.py"]
            ),
            "control: all passing self-tests exit 0": run_all(good) == 0,
            "a planted failing self-test exits 1": run_all(bad) == 1,
            "finding no self-test exits 1": run_all(empty) == 1,
        }
    print()
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--root", type=Path, default=Path("."), help="directory to search (default: .)"
    )
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    return self_test() if args.self_test else run_all(args.root.resolve())


if __name__ == "__main__":
    sys.exit(main())
