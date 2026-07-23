from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parents[2]
RESOURCES = ROOT / "src" / "wattwraith" / "resources"


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["POLARS_SKIP_CPU_CHECK"] = "1"
    environment["LOKY_MAX_CPU_COUNT"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "wattwraith.cli", *arguments],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )


def test_demo_writes_real_json_csv_and_html(tmp_path: Path) -> None:
    output = tmp_path / "demo"
    completed = _run_cli("demo", "--output-dir", str(output))
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["devices"] == 4
    assert summary["status"] == "ok"
    json_path = output / "wattwraith-report.json"
    csv_path = output / "wattwraith-report.csv"
    html_path = output / "wattwraith-report.html"
    assert json_path.is_file() and csv_path.is_file() and html_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(payload["reports"]) == 4
    assert {result["kind"] for result in payload["reports"][0]["results"]} == {
        "baseline",
        "periodic_standby",
        "overnight_sustained",
        "anomaly_spike",
    }
    assert "confidence" in csv_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in html_path.read_text(encoding="utf-8")


def test_analyze_json_applies_tariff_override(tmp_path: Path) -> None:
    output = tmp_path / "repriced"
    completed = _run_cli(
        "analyze",
        str(RESOURCES / "smart_plug_week.json"),
        "--annotations",
        str(RESOURCES / "annotations.json"),
        "--tariff",
        str(RESOURCES / "tariff.json"),
        "--price-per-kwh",
        "1.24",
        "--currency",
        "CNY",
        "--output-dir",
        str(output),
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["price_per_kwh"] == "1.24"
    payload = json.loads(
        (output / "wattwraith-report.json").read_text(encoding="utf-8")
    )
    assert all(report["tariff"]["price_per_kwh"] == "1.24" for report in payload["reports"])
    assert any(report["savings"]["estimates"] for report in payload["reports"])


def test_bad_input_returns_nonzero_without_traceback(tmp_path: Path) -> None:
    invalid = tmp_path / "bad.csv"
    invalid.write_text("wrong,columns\n1,2\n", encoding="utf-8")
    completed = _run_cli(
        "analyze",
        str(invalid),
        "--output-dir",
        str(tmp_path / "output"),
    )
    assert completed.returncode == 2
    assert "error:" in completed.stderr
    assert "required columns" in completed.stderr.lower()
    assert "traceback" not in completed.stderr.lower()
