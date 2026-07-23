from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from wattwraith.adapters import DataLoadError, load_annotations, load_power_file, load_tariff
from wattwraith.domain import DetectionStatus, FindingKind
from wattwraith.services import analyze_frame, reports_to_csv, reports_to_html, reports_to_json

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "examples" / "data"


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 13, tzinfo=UTC)


def test_csv_and_json_load_to_equivalent_frames() -> None:
    csv_frame = load_power_file(DATA / "smart_plug_week.csv")
    json_frame = load_power_file(DATA / "smart_plug_week.json")
    assert csv_frame.shape == (8064, 3)
    assert csv_frame.equals(json_frame)


@pytest.mark.integration
def test_committed_fixture_exercises_required_detection_and_exports() -> None:
    frame = load_power_file(DATA / "smart_plug_week.csv")
    reports = analyze_frame(
        frame,
        load_annotations(ROOT / "examples" / "annotations.json"),
        load_tariff(ROOT / "examples" / "tariff.json"),
        clock=FixedClock(),
    )
    detected = {
        result.kind
        for report in reports
        for result in report.results
        if result.status == DetectionStatus.DETECTED
    }
    assert {
        FindingKind.BASELINE,
        FindingKind.PERIODIC_STANDBY,
        FindingKind.OVERNIGHT_SUSTAINED,
    }.issubset(detected)
    assert len(reports) == 4
    assert all(report.privacy_notice for report in reports)
    assert '"reports": [' in reports_to_json(reports)
    assert "confidence_grade" in reports_to_csv(reports)
    assert "SYNTHETIC DATA ONLY" in reports_to_html(reports)


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("bad.txt", "x", "Supported input extensions"),
        ("bad.json", "{", "Could not parse input"),
        (
            "missing.csv",
            "timestamp,watts\n2026-01-01T00:00:00Z,1\n",
            "Missing required columns",
        ),
        (
            "negative.csv",
            "timestamp,device_id,watts\n2026-01-01T00:00:00Z,x,-1\n",
            "non-negative",
        ),
    ],
)
def test_loader_reports_safe_errors(
    tmp_path: Path, filename: str, content: str, message: str
) -> None:
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DataLoadError, match=message):
        load_power_file(path)


def test_missing_file_error_does_not_echo_parent_path(tmp_path: Path) -> None:
    secret_parent = tmp_path / "token-is-private"
    path = secret_parent / "missing.csv"
    with pytest.raises(DataLoadError) as caught:
        load_power_file(path)
    assert "token-is-private" not in str(caught.value)


def test_html_and_csv_escape_user_labels() -> None:
    frame = pl.DataFrame(
        {
            "timestamp": [
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 1, 2, tzinfo=UTC),
            ],
            "device_id": ["x", "x", "x"],
            "watts": [5.0, 5.0, 5.0],
        }
    )
    from wattwraith.domain import DeviceAnnotation, TariffPlan

    reports = analyze_frame(
        frame,
        {"x": DeviceAnnotation(device_id="x", display_name="=2+2<script>")},
        TariffPlan(price_per_kwh="0.2"),
        clock=FixedClock(),
    )
    assert "'=2+2<script>" in reports_to_csv(reports)
    html_output = reports_to_html(reports)
    assert "<script>" not in html_output
    assert "&lt;script&gt;" in html_output


def test_json_export_has_no_raw_rows_or_source_paths() -> None:
    payload = json.loads(
        reports_to_json(
            analyze_frame(
                load_power_file(DATA / "smart_plug_week.csv").filter(
                    pl.col("device_id") == "television"
                ),
                load_annotations(ROOT / "examples" / "annotations.json"),
                load_tariff(ROOT / "examples" / "tariff.json"),
                clock=FixedClock(),
            )
        )
    )
    serialized = json.dumps(payload)
    assert "smart_plug_week.csv" not in serialized
    assert '"watts"' not in serialized
