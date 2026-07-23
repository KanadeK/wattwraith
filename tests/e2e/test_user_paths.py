from __future__ import annotations

import json
from pathlib import Path

from wattwraith.cli import main

ROOT = Path(__file__).resolve().parents[2]


def test_demo_user_path_writes_three_real_reports(
    tmp_path: Path,
    capsys: object,
) -> None:
    output_dir = tmp_path / "demo-output"
    status = main(
        [
            "demo",
            "--price-per-kwh",
            "0.75",
            "--currency",
            "CNY",
            "--output-dir",
            str(output_dir),
        ]
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    summary = json.loads(captured.out)

    assert status == 0
    assert summary["status"] == "ok"
    assert summary["devices"] == 4
    assert summary["price_per_kwh"] == "0.75"
    assert set(summary["outputs"]) == {"json", "csv", "html"}
    assert all(Path(path).is_file() for path in summary["outputs"].values())
    report = json.loads((output_dir / "wattwraith-report.json").read_text(encoding="utf-8"))
    assert len(report["reports"]) == 4
    assert all(item["results"] for item in report["reports"])


def test_analyze_user_path_accepts_json_and_explicit_configuration(
    tmp_path: Path,
    capsys: object,
) -> None:
    output_dir = tmp_path / "analysis-output"
    status = main(
        [
            "analyze",
            str(ROOT / "examples" / "data" / "smart_plug_week.json"),
            "--annotations",
            str(ROOT / "examples" / "annotations.json"),
            "--tariff",
            str(ROOT / "examples" / "tariff.json"),
            "--output-dir",
            str(output_dir),
        ]
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    summary = json.loads(captured.out)

    assert status == 0
    assert summary["devices"] == 4
    csv_output = (output_dir / "wattwraith-report.csv").read_text(encoding="utf-8")
    html_output = (output_dir / "wattwraith-report.html").read_text(encoding="utf-8")
    assert "confidence_grade" in csv_output
    assert "Projected avoidable energy" in html_output


def test_invalid_input_user_path_fails_without_partial_outputs(
    tmp_path: Path,
    capsys: object,
) -> None:
    output_dir = tmp_path / "must-not-exist"
    status = main(
        [
            "analyze",
            str(tmp_path / "private-parent" / "missing.csv"),
            "--output-dir",
            str(output_dir),
        ]
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]

    assert status == 2
    assert "error:" in captured.err
    assert "private-parent" not in captured.err
    assert not output_dir.exists()
