"""Generate deterministic, openly licensed smart-plug fixtures."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 32
CADENCE_MINUTES = 5
DAYS = 7
START = datetime(2026, 1, 5, tzinfo=UTC)
DEVICE_IDS = ("refrigerator", "television", "game_console", "printer")


def _noise(rng: random.Random, scale: float) -> float:
    return rng.uniform(-scale, scale)


def _watts(device_id: str, index: int, timestamp: datetime, rng: random.Random) -> float:
    minute = timestamp.hour * 60 + timestamp.minute
    if device_id == "refrigerator":
        cycle_minute = (index * CADENCE_MINUTES) % 90
        value = 88.0 if cycle_minute < 25 else 3.1
        if index == 777:
            value = 310.0
        return max(0.0, value + _noise(rng, 1.2))
    if device_id == "television":
        value = 72.0 if 18 * 60 <= minute < 22 * 60 else 5.2
        return max(0.0, value + _noise(rng, 0.7))
    if device_id == "game_console":
        if 19 * 60 <= minute < 23 * 60:
            value = 148.0
        elif minute >= 23 * 60 or minute < 7 * 60:
            value = 11.8
        else:
            value = 0.4
        return max(0.0, value + _noise(rng, 0.5))
    if device_id == "printer":
        cycle_minute = (index * CADENCE_MINUTES) % (6 * 60)
        value = 18.0 if cycle_minute < 20 else 2.2
        if index == 1100:
            value = 225.0
        return max(0.0, value + _noise(rng, 0.35))
    raise ValueError(f"Unsupported fixture device: {device_id}")


def generate_rows() -> list[dict[str, str | float]]:
    """Return the same seven-day fixture for every invocation."""
    rng = random.Random(SEED)
    rows: list[dict[str, str | float]] = []
    sample_count = DAYS * 24 * 60 // CADENCE_MINUTES
    for index in range(sample_count):
        timestamp = START + timedelta(minutes=index * CADENCE_MINUTES)
        for device_id in DEVICE_IDS:
            value = _watts(device_id, index, timestamp, rng)
            rows.append(
                {
                    "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                    "device_id": device_id,
                    "watts": round(value, 3),
                }
            )
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "examples" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = generate_rows()

    csv_path = output_dir / "smart_plug_week.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("timestamp", "device_id", "watts"))
        writer.writeheader()
        writer.writerows(rows)

    json_path = output_dir / "smart_plug_week.json"
    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    manifest = {
        "seed": SEED,
        "cadence_minutes": CADENCE_MINUTES,
        "days": DAYS,
        "rows": len(rows),
        "devices": list(DEVICE_IDS),
        "files": {
            csv_path.name: _sha256(csv_path),
            json_path.name: _sha256(json_path),
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    resource_dir = root / "src" / "wattwraith" / "resources"
    resource_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(csv_path, resource_dir / csv_path.name)
    shutil.copyfile(json_path, resource_dir / json_path.name)
    shutil.copyfile(root / "examples" / "annotations.json", resource_dir / "annotations.json")
    shutil.copyfile(root / "examples" / "tariff.json", resource_dir / "tariff.json")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
