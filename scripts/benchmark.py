"""Measure the committed four-device fixture and update benchmark evidence."""

from __future__ import annotations

import platform
import statistics
import time
from datetime import UTC, datetime

from _common import ROOT

from wattwraith.adapters import load_annotations, load_power_file, load_tariff
from wattwraith.services import analyze_frame


class BenchmarkClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 13, tzinfo=UTC)


def main() -> int:
    frame = load_power_file(ROOT / "examples" / "data" / "smart_plug_week.csv")
    annotations = load_annotations(ROOT / "examples" / "annotations.json")
    tariff = load_tariff(ROOT / "examples" / "tariff.json")
    timings: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        reports = analyze_frame(frame, annotations, tariff, clock=BenchmarkClock())
        timings.append(time.perf_counter() - started)
    ordered = sorted(timings)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    content = f"""# Benchmark

Measured on 2026-07-23 with the committed deterministic fixture.

| Field | Value |
| --- | --- |
| Machine | {platform.platform()} |
| Python | {platform.python_version()} |
| Rows | {frame.height} |
| Devices | {len(reports)} |
| Repetitions | {len(timings)} |
| Median | {statistics.median(timings):.3f} seconds |
| p95 | {p95:.3f} seconds |

Command: `python scripts/benchmark.py`

This is an end-to-end local analysis benchmark, including deterministic clustering
and anomaly detection. It is not a smart-plug ingestion throughput claim.
"""
    (ROOT / "docs" / "BENCHMARK.md").write_text(content, encoding="utf-8")
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
