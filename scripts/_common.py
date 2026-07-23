"""Shared helpers for cross-platform repository tasks."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def task_environment() -> dict[str, str]:
    """Return deterministic environment settings without masking command failures."""
    environment = os.environ.copy()
    if sys.platform == "win32":
        environment.setdefault("POLARS_SKIP_CPU_CHECK", "1")
        environment.setdefault("LOKY_MAX_CPU_COUNT", "2")
    environment.setdefault("PYTHONUTF8", "1")
    return environment


def run(command: Sequence[str], *, cwd: Path = ROOT) -> None:
    """Run a visible command and stop at its real non-zero exit status."""
    print("+", subprocess.list2cmdline(list(command)), flush=True)
    subprocess.run(
        list(command),
        cwd=cwd,
        env=task_environment(),
        check=True,
    )


def ensure_within_root(path: Path) -> Path:
    """Resolve a generated path and reject targets outside this repository."""
    resolved = path.resolve()
    resolved.relative_to(ROOT.resolve())
    return resolved
