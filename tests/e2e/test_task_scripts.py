from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]


def test_documented_demo_script_runs_from_checkout() -> None:
    environment = os.environ.copy()
    environment["POLARS_SKIP_CPU_CHECK"] = "1"
    environment["LOKY_MAX_CPU_COUNT"] = "1"
    completed = subprocess.run(
        [sys.executable, "scripts/demo.py"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (ROOT / "site" / "index.html").stat().st_size > 1000
    assert (ROOT / "site" / "report.json").stat().st_size > 1000


def test_screenshot_script_scrolls_to_result_without_clicking_heading_anchor() -> None:
    source = (ROOT / "scripts" / "capture_screenshots.py").read_text(encoding="utf-8")
    assert "scroll_into_view_if_needed()" in source
    assert 'get_by_text("31.536 kWh", exact=True).wait_for()' in source
    assert "game-console-synthetic" not in source
