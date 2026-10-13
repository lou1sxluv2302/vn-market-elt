"""Read project config (`config/*.yml`) and local environment values.

Constants live in `config/*.yml` (committed). Environment values - project id,
local paths - live in `config/env/prod.yml`, which is git-ignored; only
`config/env/prod.example.yml` is committed (spec §14.5).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
ENV_FILE = CONFIG_DIR / "env" / "prod.yml"


def load_config(name: str, config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    """Return `config/<name>.yml` as a dict."""
    return yaml.safe_load((config_dir / f"{name}.yml").read_text(encoding="utf-8"))


def load_env(env_file: Path = ENV_FILE) -> dict[str, Any]:
    """Return the local environment values; raise with a clear message if the file is missing."""
    if not env_file.exists():
        raise FileNotFoundError(
            f"{env_file} is missing: copy config/env/prod.example.yml to it and fill it in"
        )
    return yaml.safe_load(env_file.read_text(encoding="utf-8"))


def utf8_stdio() -> None:
    """Windows pipes default to cp1252, which cannot print ✅/🔴: force UTF-8 first."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
