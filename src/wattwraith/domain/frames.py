"""Canonical Polars frame validation and gap-aware time-series utilities."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import isfinite
from statistics import median

import polars as pl

from wattwraith.domain.models import AnalysisConfig


class FrameValidationError(ValueError):
    """Raised when smart-plug data cannot safely enter the domain core."""


@dataclass(frozen=True)
class NormalizedSeries:
    frame: pl.DataFrame
    cadence_seconds: float
    coverage: float
    warnings: tuple[str, ...]


def _timestamp_dtype_is_aware(dtype: pl.DataType) -> bool:
    return isinstance(dtype, pl.Datetime) and dtype.time_zone is not None


def validate_and_normalize_frame(
    frame: pl.DataFrame,
    *,
    config: AnalysisConfig,
) -> NormalizedSeries:
    """Validate one device and normalize timestamps to sorted UTC microseconds."""

    required = {"timestamp", "device_id", "watts"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise FrameValidationError(f"missing required columns: {', '.join(missing)}")
    if frame.height < 2:
        raise FrameValidationError("at least two readings are required")
    if frame.height > config.max_rows:
        raise FrameValidationError(f"input exceeds the {config.max_rows} row safety limit")

    selected = frame.select("timestamp", "device_id", "watts")
    if not _timestamp_dtype_is_aware(selected.schema["timestamp"]):
        raise FrameValidationError("timestamp must be timezone-aware")

    selected = selected.with_columns(
        pl.col("timestamp")
        .dt.convert_time_zone("UTC")
        .cast(pl.Datetime(time_unit="us", time_zone="UTC")),
        pl.col("device_id").cast(pl.String),
        pl.col("watts").cast(pl.Float64),
    )
    if any(value > 0 for value in selected.null_count().row(0)):
        raise FrameValidationError("timestamp, device_id, and watts cannot contain nulls")

    device_ids = selected.get_column("device_id").unique().to_list()
    if len(device_ids) != 1:
        raise FrameValidationError("analyze_device accepts exactly one device_id")
    if not device_ids[0] or not str(device_ids[0]).strip():
        raise FrameValidationError("device_id cannot be empty")

    watts = selected.get_column("watts").to_list()
    if any(not isfinite(value) for value in watts):
        raise FrameValidationError("watts must be finite")
    if any(value < 0.0 or value > 100_000.0 for value in watts):
        raise FrameValidationError("watts must be between 0 and 100000")

    grouped = (
        selected.group_by("device_id", "timestamp")
        .agg(
            pl.col("watts").mean().alias("watts"),
            pl.len().alias("_duplicate_size"),
        )
        .sort("timestamp")
    )
    duplicates = selected.height - grouped.height
    warnings: list[str] = []
    if duplicates:
        duplicate_ratio = duplicates / selected.height
        warnings.append(
            f"Aggregated {duplicates} duplicate timestamp row(s) by mean power "
            f"({duplicate_ratio:.2%} of input)."
        )
        if duplicate_ratio > 0.01:
            warnings.append("Duplicate rate exceeds 1%; detector confidence is reduced.")

    normalized = grouped.drop("_duplicate_size")
    if normalized.height < 2:
        raise FrameValidationError("timestamps must span at least two distinct instants")
    cadence = infer_cadence_seconds(normalized)
    coverage = compute_coverage(
        normalized,
        cadence_seconds=cadence,
        max_gap_factor=config.max_gap_factor,
    )
    return NormalizedSeries(normalized, cadence, coverage, tuple(warnings))


def infer_cadence_seconds(frame: pl.DataFrame) -> float:
    """Infer nominal cadence from the median positive timestamp delta."""

    timestamps = frame.get_column("timestamp").to_list()
    differences = [
        (right - left).total_seconds() for left, right in pairwise(timestamps) if right > left
    ]
    if not differences:
        raise FrameValidationError("timestamps must have a positive span")
    cadence = float(median(differences))
    if not isfinite(cadence) or cadence <= 0:
        raise FrameValidationError("could not infer a positive cadence")
    return cadence


def compute_coverage(
    frame: pl.DataFrame,
    *,
    cadence_seconds: float,
    max_gap_factor: float,
) -> float:
    """Return the fraction of wall-clock span represented by valid intervals."""

    timestamps = frame.get_column("timestamp").to_list()
    total_span = (timestamps[-1] - timestamps[0]).total_seconds()
    if total_span <= 0:
        raise FrameValidationError("timestamps must have a positive span")
    valid_seconds = sum(
        delta
        for left, right in pairwise(timestamps)
        if 0 < (delta := (right - left).total_seconds()) <= cadence_seconds * max_gap_factor
    )
    return float(max(0.0, min(1.0, valid_seconds / total_span)))


def gap_aware_energy_wh(
    timestamps: list[object],
    power_w: list[float],
    *,
    cadence_seconds: float,
    max_gap_factor: float,
) -> tuple[float, float]:
    """Integrate with the trapezoid rule and return energy plus valid seconds."""

    if len(timestamps) != len(power_w):
        raise ValueError("timestamps and power_w must have equal length")
    energy_wh = 0.0
    valid_seconds = 0.0
    for index in range(len(timestamps) - 1):
        left = timestamps[index]
        right = timestamps[index + 1]
        delta = (right - left).total_seconds()  # type: ignore[operator]
        if 0 < delta <= cadence_seconds * max_gap_factor:
            energy_wh += (power_w[index] + power_w[index + 1]) * 0.5 * delta / 3600
            valid_seconds += delta
    return energy_wh, valid_seconds
