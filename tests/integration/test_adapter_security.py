from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from wattwraith.adapters import DataLoadError, load_annotations, load_power_file, load_tariff
from wattwraith.domain import DeviceAnnotation, TariffPlan
from wattwraith.services import analyze_frame, reports_to_csv, reports_to_html, reports_to_json

ROOT = Path(__file__).resolve().parents[2]


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 23, 12, tzinfo=UTC)


def _small_frame(device_id: str = "plug-1") -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=index) for index in range(72)],
            "device_id": [device_id] * 72,
            "watts": [5.0] * 72,
        },
        schema_overrides={"timestamp": pl.Datetime("us", "UTC")},
    )


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "empty"),
        ("[]", "non-empty array"),
        ("{}", "non-empty array"),
    ],
)
def test_empty_and_non_array_inputs_are_rejected(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    path = tmp_path / "readings.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DataLoadError, match=message):
        load_power_file(path)


def test_size_limit_is_enforced_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "readings.csv"
    path.write_text("timestamp,device_id,watts\n", encoding="utf-8")
    with pytest.raises(DataLoadError, match="safety limit"):
        load_power_file(path, max_bytes=4)


def test_permission_failure_is_safe_and_does_not_disclose_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_parent = tmp_path / "api-token-private"
    private_parent.mkdir()
    path = private_parent / "readings.json"
    path.write_text("[]", encoding="utf-8")
    original_stat = Path.stat

    def denied_stat(candidate: Path, *args: object, **kwargs: object) -> object:
        if candidate == path:
            raise PermissionError("secret operating-system detail")
        return original_stat(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", denied_stat)
    with pytest.raises(DataLoadError) as caught:
        load_power_file(path)
    message = str(caught.value)
    assert "cannot be read" in message
    assert "api-token-private" not in message
    assert "secret operating-system detail" not in message


def test_invalid_annotation_and_tariff_configs_fail_closed(tmp_path: Path) -> None:
    annotations = tmp_path / "annotations.json"
    annotations.write_text(
        json.dumps({"plug-1": {"device_type": "guessed-personal-device"}}),
        encoding="utf-8",
    )
    tariff = tmp_path / "tariff.json"
    tariff.write_text(
        json.dumps({"currency": "US", "price_per_kwh": "-1"}),
        encoding="utf-8",
    )

    with pytest.raises(DataLoadError, match="annotations failed validation"):
        load_annotations(annotations)
    with pytest.raises(DataLoadError, match="Tariff configuration failed validation"):
        load_tariff(tariff)


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_csv_export_neutralizes_every_formula_prefix(prefix: str) -> None:
    device_id = f"{prefix}formula"
    reports = analyze_frame(
        _small_frame(device_id),
        {
            device_id: DeviceAnnotation(
                device_id=device_id,
                display_name=f"{prefix}display",
                standby_target_w=1.0,
            )
        },
        TariffPlan(currency="USD", price_per_kwh="0.20"),
        clock=FixedClock(),
    )
    rows = list(csv.DictReader(io.StringIO(reports_to_csv(reports))))
    assert rows
    assert all(row["device_id"].startswith(f"'{prefix}") for row in rows)
    assert all(row["display_name"].startswith(f"'{prefix}") for row in rows)


def test_html_escapes_untrusted_labels_and_json_excludes_raw_data() -> None:
    label = '<img src=x onerror="alert(1)">&private'
    reports = analyze_frame(
        _small_frame(),
        {
            "plug-1": DeviceAnnotation(
                device_id="plug-1",
                display_name=label,
                standby_target_w=1.0,
            )
        },
        TariffPlan(currency="USD", price_per_kwh="0.20"),
        clock=FixedClock(),
    )
    html_output = reports_to_html(reports)
    json_output = reports_to_json(reports)

    assert "<img" not in html_output
    assert "&lt;img" in html_output
    assert "onerror=&quot;alert(1)&quot;" in html_output
    assert '"watts"' not in json_output
    assert "source_path" not in json_output
    assert "occupancy inference" not in json_output.lower()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.integration
def test_fixture_generator_reproduces_committed_artifacts(tmp_path: Path) -> None:
    isolated_root = tmp_path / "wattwraith"
    scripts = isolated_root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "generate_samples.py", scripts / "generate_samples.py")
    examples = isolated_root / "examples"
    examples.mkdir()
    shutil.copy2(ROOT / "examples" / "annotations.json", examples / "annotations.json")
    shutil.copy2(ROOT / "examples" / "tariff.json", examples / "tariff.json")

    completed = subprocess.run(
        [sys.executable, str(scripts / "generate_samples.py")],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    generated = isolated_root / "examples" / "data"
    committed = ROOT / "examples" / "data"
    assert _sha256(generated / "smart_plug_week.csv") == _sha256(committed / "smart_plug_week.csv")
    assert _sha256(generated / "smart_plug_week.json") == _sha256(
        committed / "smart_plug_week.json"
    )
    assert json.loads((generated / "manifest.json").read_text(encoding="utf-8")) == json.loads(
        (committed / "manifest.json").read_text(encoding="utf-8")
    )
