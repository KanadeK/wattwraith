"""Multi-device analysis orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import polars as pl

from wattwraith.adapters import load_power_file
from wattwraith.domain import (
    AnalysisConfig,
    AnalysisReport,
    Clock,
    DeviceAnnotation,
    TariffPlan,
    analyze_device,
)


def analyze_frame(
    frame: pl.DataFrame,
    annotations: Mapping[str, DeviceAnnotation],
    tariff: TariffPlan,
    *,
    config: AnalysisConfig | None = None,
    clock: Clock | None = None,
) -> tuple[AnalysisReport, ...]:
    """Analyze every device independently using explicit annotations."""
    device_ids = sorted(frame.get_column("device_id").unique().to_list())
    reports: list[AnalysisReport] = []
    for device_id in device_ids:
        annotation = annotations.get(
            device_id,
            DeviceAnnotation(device_id=device_id, annotation_origin="user"),
        )
        device_frame = frame.filter(pl.col("device_id") == device_id)
        reports.append(
            analyze_device(
                device_frame,
                annotation,
                tariff,
                config=config,
                clock=clock,
            )
        )
    return tuple(reports)


def analyze_file(
    path: str | Path,
    annotations: Mapping[str, DeviceAnnotation],
    tariff: TariffPlan,
    *,
    config: AnalysisConfig | None = None,
    clock: Clock | None = None,
) -> tuple[AnalysisReport, ...]:
    """Load and analyze a bounded local CSV or JSON file."""
    return analyze_frame(
        load_power_file(path),
        annotations,
        tariff,
        config=config,
        clock=clock,
    )
