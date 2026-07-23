"""Local, bounded CSV and JSON adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import ValidationError

from wattwraith.domain import DeviceAnnotation, TariffPlan

REQUIRED_COLUMNS = {"timestamp", "device_id", "watts"}
MAX_FILE_BYTES = 50 * 1024 * 1024


class DataLoadError(ValueError):
    """Safe error raised when a local input cannot be validated."""


def _bounded_file(path: str | Path, *, max_bytes: int = MAX_FILE_BYTES) -> Path:
    candidate = Path(path)
    try:
        size = candidate.stat().st_size
    except FileNotFoundError as exc:
        raise DataLoadError(f"Input file does not exist: {candidate.name}") from exc
    except PermissionError as exc:
        raise DataLoadError(f"Input file cannot be read: {candidate.name}") from exc
    if not candidate.is_file():
        raise DataLoadError(f"Input path is not a file: {candidate.name}")
    if size <= 0:
        raise DataLoadError(f"Input file is empty: {candidate.name}")
    if size > max_bytes:
        raise DataLoadError(f"Input file exceeds the {max_bytes // (1024 * 1024)} MiB safety limit")
    return candidate


def _normalize_columns(frame: pl.DataFrame) -> pl.DataFrame:
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise DataLoadError(f"Missing required columns: {', '.join(sorted(missing))}")
    try:
        timestamp_dtype = frame.schema["timestamp"]
        timestamp_expr = pl.col("timestamp")
        if timestamp_dtype == pl.String:
            timestamp_expr = timestamp_expr.str.to_datetime(strict=True, time_zone="UTC")
        elif isinstance(timestamp_dtype, pl.Datetime):
            if timestamp_dtype.time_zone is None:
                raise DataLoadError(
                    "Naive timestamps are not accepted; include an explicit UTC offset"
                )
            timestamp_expr = timestamp_expr.dt.convert_time_zone("UTC")
        else:
            raise DataLoadError("timestamp must contain ISO-8601 strings or datetimes")
        normalized = frame.select(
            timestamp_expr.alias("timestamp"),
            pl.col("device_id").cast(pl.String, strict=True).str.strip_chars(),
            pl.col("watts").cast(pl.Float64, strict=True),
        )
    except DataLoadError:
        raise
    except (pl.exceptions.PolarsError, TypeError, ValueError) as exc:
        raise DataLoadError("Could not parse timestamp, device_id, or watts columns") from exc
    if normalized.null_count().sum_horizontal().item() != 0:
        raise DataLoadError("Required columns must not contain null values")
    if normalized.filter(pl.col("device_id").str.len_chars() == 0).height:
        raise DataLoadError("device_id must not be blank")
    if normalized.filter(~pl.col("watts").is_finite() | (pl.col("watts") < 0)).height:
        raise DataLoadError("watts must contain finite, non-negative values")
    return normalized


def load_power_file(path: str | Path, *, max_bytes: int = MAX_FILE_BYTES) -> pl.DataFrame:
    """Load a CSV or JSON array into the canonical domain schema."""
    candidate = _bounded_file(path, max_bytes=max_bytes)
    try:
        if candidate.suffix.lower() == ".csv":
            frame = pl.read_csv(candidate)
        elif candidate.suffix.lower() == ".json":
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if not isinstance(payload, list) or not payload:
                raise DataLoadError("JSON input must be a non-empty array of readings")
            frame = pl.from_dicts(payload)
        else:
            raise DataLoadError("Supported input extensions are .csv and .json")
    except DataLoadError:
        raise
    except PermissionError as exc:
        raise DataLoadError(f"Input file cannot be read: {candidate.name}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError, pl.exceptions.PolarsError) as exc:
        raise DataLoadError(f"Could not parse input file: {candidate.name}") from exc
    return _normalize_columns(frame)


def _read_object(path: str | Path) -> dict[str, Any]:
    candidate = _bounded_file(path, max_bytes=1024 * 1024)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, PermissionError) as exc:
        raise DataLoadError(f"Could not parse configuration: {candidate.name}") from exc
    if not isinstance(payload, dict):
        raise DataLoadError("Configuration must be a JSON object")
    return payload


def load_annotations(path: str | Path) -> dict[str, DeviceAnnotation]:
    """Load user or fixture annotations without inferring device types."""
    payload = _read_object(path)
    try:
        return {
            device_id: DeviceAnnotation(device_id=device_id, **values)
            for device_id, values in payload.items()
            if isinstance(values, dict)
        }
    except (TypeError, ValidationError) as exc:
        raise DataLoadError("Device annotations failed validation") from exc


def load_tariff(path: str | Path) -> TariffPlan:
    """Load the flat v0.1 tariff contract."""
    try:
        return TariffPlan.model_validate(_read_object(path))
    except ValidationError as exc:
        raise DataLoadError("Tariff configuration failed validation") from exc
