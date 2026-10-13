"""Check that a tool pinned in two places carries the same version in both.

Dependabot bumps `pyproject.toml` but not `.pre-commit-config.yaml`, and neither
Dependabot nor `pre-commit autoupdate` touches a version held in a workflow
variable, so a bump on one side leaves CI and the local hooks on different
versions. Each pair below names the two places one version lives. Staleness
(a newer release exists) is reported by the weekly `hooks-current` job.

Exit codes: 0 = every pair matches · 1 = a pair differs or a version is missing.

Usage:
    python tools/check_pins.py [--root PATH]
    python tools/check_pins.py --self-test
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import yaml


def pyproject_pin(package: str) -> Callable[[Path], str | None]:
    def read(root: Path) -> str | None:
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(rf'"{re.escape(package)}==([^"]+)"', text)
        return m.group(1) if m else None
    return read


def pre_commit_rev(repo_url: str) -> Callable[[Path], str | None]:
    def read(root: Path) -> str | None:
        config = yaml.safe_load((root / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
        for repo in config.get("repos", []):
            if repo.get("repo") == repo_url:
                return str(repo.get("rev", "")).removeprefix("v") or None
        return None
    return read


def workflow_env(workflow: str, name: str) -> Callable[[Path], str | None]:
    def read(root: Path) -> str | None:
        text = (root / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        m = re.search(rf"^\s*{re.escape(name)}:\s*['\"]?([^'\"\s#]+)", text, re.M)
        return m.group(1) if m else None
    return read


PAIRS = {
    "ruff": (
        ("pyproject.toml", pyproject_pin("ruff")),
        (".pre-commit-config.yaml", pre_commit_rev("https://github.com/astral-sh/ruff-pre-commit")),
    ),
    "gitleaks": (
        (".pre-commit-config.yaml", pre_commit_rev("https://github.com/gitleaks/gitleaks")),
        ("workflows/security.yml", workflow_env("security.yml", "GITLEAKS_VERSION")),
    ),
}


def check(root: Path) -> int:
    failed = 0
    for tool, ((where_a, read_a), (where_b, read_b)) in PAIRS.items():
        try:
            a, b = read_a(root), read_b(root)
        except FileNotFoundError as exc:
            a = b = None
            print(f"🔴 {tool}: {exc.filename} not found")
        ok = a is not None and a == b
        failed += not ok
        print(f"{'✅' if ok else '🔴'} {tool}: {where_a} {a} · {where_b} {b}")
    return 1 if failed else 0


def self_test() -> int:
    """Known answers: matching pins pass; a bump on one side only fails; a missing pin fails."""
    def make(root: Path, ruff: str, gitleaks_workflow: str | None) -> Path:
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "pyproject.toml").write_text(
            f'dev = ["ruff=={ruff}", "pre-commit==4.6.2"]\n', encoding="utf-8"
        )
        (root / ".pre-commit-config.yaml").write_text(
            "repos:\n"
            "  - repo: https://github.com/gitleaks/gitleaks\n    rev: v8.30.0\n"
            "  - repo: https://github.com/astral-sh/ruff-pre-commit\n    rev: v0.17.0\n",
            encoding="utf-8",
        )
        env = f"    GITLEAKS_VERSION: {gitleaks_workflow}\n" if gitleaks_workflow else ""
        (root / ".github" / "workflows" / "security.yml").write_text(
            f"env:\n{env}    OTHER: 1\n", encoding="utf-8"
        )
        return root

    with tempfile.TemporaryDirectory() as tmp:
        cases = {
            "control: matching pins exit 0": (make(Path(tmp, "a"), "0.17.0", "8.30.0"), 0),
            "ruff bumped in pyproject only exits 1": (make(Path(tmp, "b"), "0.18.0", "8.30.0"), 1),
            "gitleaks bumped in the workflow only exits 1": (
                make(Path(tmp, "c"), "0.17.0", "8.31.0"), 1
            ),
            "a missing pin exits 1": (make(Path(tmp, "d"), "0.17.0", None), 1),
        }
        results = {name: check(root) == expected for name, (root, expected) in cases.items()}
    results["an unknown argument is rejected with exit 2"] = subprocess.run(  # noqa: S603
        [sys.executable, __file__, "--bogus"], capture_output=True, timeout=60
    ).returncode == 2
    print()
    for name, ok in results.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(results.values()) else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--root", type=Path, default=Path("."), help="repository root (default: .)"
    )
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    return self_test() if args.self_test else check(args.root)


if __name__ == "__main__":
    sys.exit(main())
