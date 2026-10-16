"""Scan every object in a git repository for secrets and identifying details.

Every blob is scanned - reachable or not, so amended or rebased-away commits are
covered too. Values are printed redacted (first and last four characters only).

Exit codes: 0 = no secret found · 1 = at least one secret found · 2 = usage or
git error. Identifying details (e-mail addresses, local Windows paths, vendor
licence markers) are reported as warnings and do not change the exit code.

Usage:
    python tools/secret_scan.py [--repo PATH]
    python tools/secret_scan.py --self-test
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

GIT_TIMEOUT_SECONDS = 60

SECRET_PATTERNS = {
    "aws_access_key": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "gcp_api_key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "gcp_service_account_key": r"\"private_key\"\s*:\s*\"-----BEGIN",
    "private_key_block": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
    "github_token": (
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b"
    ),
    "slack_token": r"\bxox[abpors]-[A-Za-z0-9-]{10,}\b",
    "stripe_key": r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b",
    "stripe_webhook_secret": r"\bwhsec_[A-Za-z0-9]{16,}\b",
    "jwt": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
    "connection_string": r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp|mssql)://[^\s'\"]+:[^\s'\"@]+@",
    "credentials_in_url": r"https?://[^\s/:@'\"]+:[^\s/@'\"]+@",
}
ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?key|client[_-]?secret)\b"
    r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-+/=.]{12,})"
)
PLACEHOLDER = re.compile(r"(?i)<[^>]+>|example|placeholder|your[-_]|xxxx|changeme")
WARNING_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "windows_path": r"(?i)\b[A-Z]:\\(?:Users|Work)\\[^\s`'\")|]+",
    "vendor_licence_marker": r"VNSTOCK_DEVICE_ID|lc_init\(",
}
SELF_PATH = "tools/secret_scan.py"
ALLOWED_EMAILS = {
    "noreply@anthropic.com",
    "noreply@github.com",  # committer of merges made on github.com
}
NOREPLY_SUFFIX = "@users.noreply.github.com"  # GitHub noreply addresses (people and bots)


def is_allowed_email(address: str) -> bool:
    return address in ALLOWED_EMAILS or address.endswith(NOREPLY_SUFFIX)


def redact(value: str) -> str:
    value = value.strip()
    if len(value) <= 10:
        return f"{value[:2]}… (len {len(value)})"
    return f"{value[:4]}…{value[-4:]} (len {len(value)})"


def entropy(text: str) -> float:
    counts = Counter(text)
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def git(repo: Path, *args: str) -> str:
    """Run git in `repo` with a timeout; the only process this module starts."""
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell; repo paths come from our own CLI
        ["git", "-C", str(repo), *args],  # noqa: S607 - git is resolved from PATH by design
        capture_output=True,
        check=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    return result.stdout.decode("utf-8", "replace")


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def format_finding(kind: str, blob: str, where: str, text: str, pos: int, value: str) -> str:
    return f"[{kind}] {blob[:7]} {where}:L{line_of(text, pos)} -> {redact(value)}"


def scan(repo: Path) -> tuple[list[str], list[str]]:
    """Return (secret findings, warnings), each a list of redacted lines."""
    listing = git(repo, "cat-file", "--batch-all-objects", "--batch-check")
    objects = [line.split() for line in listing.splitlines() if line]
    blobs = [o[0] for o in objects if o[1] == "blob"]
    commits = [o[0] for o in objects if o[1] == "commit"]

    paths: dict[str, set[str]] = {}
    for commit in commits:
        for line in git(repo, "ls-tree", "-r", commit).splitlines():
            meta, path = line.split("\t", 1)
            paths.setdefault(meta.split()[2], set()).add(path)

    secrets: list[str] = []
    warnings: list[str] = []
    for commit in commits:
        for email in git(repo, "show", "-s", "--format=%ae%n%ce", commit).split():
            if not is_allowed_email(email):
                warnings.append(f"[commit_email] {commit[:7]} -> {redact(email)}")

    for blob in blobs:
        text = git(repo, "cat-file", "-p", blob)
        where = ", ".join(sorted(paths.get(blob, {"<no tree>"})))

        for name, pattern in SECRET_PATTERNS.items():
            for m in re.finditer(pattern, text):
                secrets.append(format_finding(name, blob, where, text, m.start(), m.group(0)))
        for m in ASSIGNMENT.finditer(text):
            if not PLACEHOLDER.search(m.group(0)) and entropy(m.group(1)) >= 3.5:
                secrets.append(
                    format_finding("assignment", blob, where, text, m.start(), m.group(1))
                )
        if where == SELF_PATH:  # this file's own patterns would match themselves
            continue
        for name, pattern in WARNING_PATTERNS.items():
            for m in re.finditer(pattern, text):
                if name == "email" and is_allowed_email(m.group(0)):
                    continue
                warnings.append(format_finding(name, blob, where, text, m.start(), m.group(0)))
    return secrets, warnings


def report(repo: Path) -> int:
    try:
        secrets, warnings = scan(repo)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"⚪ not run: git failed on {repo}: {exc}", file=sys.stderr)
        return 2
    for line in warnings:
        print(f"WARN  {line}")
    for line in secrets:
        print(f"FAIL  {line}")
    if secrets:
        print(f"🔴 {len(secrets)} secret finding(s); {len(warnings)} warning(s)")
        return 1
    print(f"✅ no secrets; {len(warnings)} warning(s)")
    return 0


def self_test() -> int:
    """Known answers: a clean repo passes; a key hidden in an amended commit fails."""
    fake_key = "AKIA" + "Z9" * 8  # built at runtime so this file never holds a key

    def make_repo(root: Path, plant: bool) -> Path:
        repo = root / ("planted" if plant else "control")
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "174849326+lou1sxluv2302@users.noreply.github.com")
        git(repo, "config", "user.name", "self-test")
        notes = "clean text\n" + ("contact jane.doe@corp.example\n" if plant else "")
        (repo / "notes.md").write_text(notes, encoding="utf-8")
        if plant:
            (repo / "config.yml").write_text(f"aws_key: {fake_key}\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "first")
        if plant:  # remove the key from the tip: it now lives only in an unreachable commit
            (repo / "config.yml").unlink()
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "--amend", "-m", "first, key removed")
            git(repo, "config", "user.email", "jane.doe@corp.example")
            git(repo, "commit", "-q", "--allow-empty", "-m", "personal committer")
        return repo

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        control = make_repo(root, plant=False)
        planted = make_repo(root, plant=True)
        control_secrets, control_warnings = scan(control)
        planted_secrets, planted_warnings = scan(planted)
        tip_files = git(planted, "ls-files").split()

    checks = {
        "control repo has no findings": control_secrets == [],
        "control repo has no warnings (noreply author allowed)": control_warnings == [],
        "planted personal e-mail in a file is warned": any(
            "[email]" in w for w in planted_warnings
        ),
        "planted personal commit e-mail is warned": any(
            "[commit_email]" in w for w in planted_warnings
        ),
        "planted key is gone from the tip": "config.yml" not in tip_files,
        "planted key is still found in history": any(
            "aws_access_key" in s for s in planted_secrets
        ),
        "finding is redacted": all(fake_key not in s for s in planted_secrets),
        "an unknown argument is rejected with exit 2": subprocess.run(  # noqa: S603
            [sys.executable, __file__, "--bogus"], capture_output=True, timeout=60
        ).returncode
        == 2,
    }
    for name, ok in checks.items():
        print(f"{'✅' if ok else '🔴'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    # Windows pipes default to cp1252, which cannot encode ✅/🔴 and kills the process on
    # the first print - the same failure v1 hit; force UTF-8 before any output.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--repo", type=Path, default=Path("."), help="repository to scan (default: .)"
    )
    parser.add_argument("--self-test", action="store_true", help="run offline known-answer tests")
    args = parser.parse_args()  # rejects unknown arguments with exit code 2
    return self_test() if args.self_test else report(args.repo)


if __name__ == "__main__":
    sys.exit(main())
