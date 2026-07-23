"""Run the same complete quality gate used by CI."""

from __future__ import annotations

import sys

from _common import run


def main() -> int:
    python = sys.executable
    run([python, "-m", "ruff", "check", "."])
    run([python, "-m", "ruff", "format", "--check", "."])
    run([python, "-m", "mypy", "src"])
    run(
        [
            python,
            "-m",
            "pytest",
            "-q",
            "--cov=src",
            "--cov-report=term-missing",
            "--cov-report=xml",
            "--cov-fail-under=80",
        ]
    )
    run([python, "-m", "build"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
