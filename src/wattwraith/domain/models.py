"""Validated domain inputs and serializable analysis results."""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class DomainModel(BaseModel):
    """Strict immutable base class for values crossing the domain boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class FindingKind(StrEnum):
    BASELINE = "baseline"
    PERIODIC_STANDBY = "periodic_standby"
    OVERNIGHT_SUSTAINED = "overnight_sustained"
    ANOMALY_SPIKE = "anomaly_spike"


class DetectionStatus(StrEnum):
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    INSUFFICIENT_DATA = "insufficient_data"


class ConfidenceGrade(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PowerReading(DomainModel):
    """One canonical smart-plug observation."""

    timestamp: AwareDatetime
    device_id: Annotated[str, Field(min_length=1, max_length=128)]
    watts: Annotated[float, Field(ge=0.0, le=100_000.0, allow_inf_nan=False)]


class NightWindow(DomainModel):
    """A local-time analysis window; a start after end wraps over midnight."""

    start: time = time(23, 0)
    end: time = time(6, 0)

    @model_validator(mode="after")
    def nonempty(self) -> NightWindow:
        if self.start == self.end:
            raise ValueError("night window must not cover zero or twenty-four hours")
        return self


class DeviceAnnotation(DomainModel):
    """User- or fixture-supplied metadata; device type is never inferred."""

    device_id: Annotated[str, Field(min_length=1, max_length=128)]
    display_name: Annotated[str | None, Field(max_length=128)] = None
    device_type: str = "unknown"
    annotation_origin: str = "user"
    timezone: str = "UTC"
    essential: bool = False
    shutdown_allowed: bool = False
    standby_target_w: Annotated[float | None, Field(ge=0.0, le=25_000.0)] = None
    standby_max_w: Annotated[float | None, Field(gt=0.0, le=25_000.0)] = None
    night_window: NightWindow = NightWindow()

    @field_validator("device_type")
    @classmethod
    def known_device_type(cls, value: str) -> str:
        allowed = {"refrigerator", "television", "game_console", "printer", "unknown"}
        if value not in allowed:
            raise ValueError(f"device_type must be one of {sorted(allowed)}")
        return value

    @field_validator("annotation_origin")
    @classmethod
    def known_origin(cls, value: str) -> str:
        if value not in {"user", "fixture"}:
            raise ValueError("annotation_origin must be 'user' or 'fixture'")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def safe_shutdown_policy(self) -> DeviceAnnotation:
        if self.essential and self.shutdown_allowed:
            raise ValueError("an essential device cannot allow automatic shutdown")
        return self


class TariffPlan(DomainModel):
    """Flat energy tariff used by the v0.1 estimator."""

    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "USD"
    price_per_kwh: Annotated[
        Decimal,
        Field(ge=Decimal("0"), max_digits=12, decimal_places=6),
    ]


class AnalysisConfig(DomainModel):
    """Versioned deterministic thresholds for all rules."""

    off_threshold_w: Annotated[float, Field(ge=0.0)] = 1.0
    standby_max_w: Annotated[float, Field(gt=0.0)] = 25.0
    minimum_coverage: Annotated[float, Field(gt=0.0, le=1.0)] = 0.75
    max_gap_factor: Annotated[float, Field(ge=1.0)] = 2.5
    max_rows: Annotated[int, Field(ge=2)] = 5_000_000

    min_baseline_samples: Annotated[int, Field(ge=2)] = 48
    min_state_fraction: Annotated[float, Field(gt=0.0, le=0.5)] = 0.02

    min_period_minutes: Annotated[int, Field(ge=1)] = 30
    max_period_hours: Annotated[int, Field(ge=1)] = 48
    min_period_cycles: Annotated[int, Field(ge=2)] = 3
    periodic_autocorrelation_threshold: Annotated[float, Field(gt=0.0, le=1.0)] = 0.55
    periodic_interval_mad_ratio: Annotated[float, Field(gt=0.0, le=1.0)] = 0.20

    min_valid_nights: Annotated[int, Field(ge=1)] = 3
    night_min_coverage: Annotated[float, Field(gt=0.0, le=1.0)] = 0.80
    night_sustained_fraction: Annotated[float, Field(gt=0.0, le=1.0)] = 0.80
    night_pass_rate: Annotated[float, Field(gt=0.0, le=1.0)] = 0.60
    night_min_w: Annotated[float, Field(ge=0.0)] = 3.0

    spike_robust_z: Annotated[float, Field(gt=0.0)] = 6.0
    isolation_contamination: Annotated[float, Field(gt=0.0, le=0.5)] = 0.01
    random_seed: int = 32


class RuleEvidence(DomainModel):
    """Machine-readable rule evidence suitable for CLI, JSON, and UI."""

    rule_id: str
    metric: str
    observed: float | int | str
    operator: str
    threshold: float | int | str
    unit: str | None = None
    passed: bool
    explanation: str


class Confidence(DomainModel):
    """Reproducible evidence strength, explicitly not a probability."""

    score: Annotated[float, Field(ge=0.0, le=1.0)]
    grade: ConfidenceGrade
    factors: dict[str, Annotated[float, Field(ge=0.0, le=1.0)]]


class Episode(DomainModel):
    start: AwareDatetime
    end: AwareDatetime
    peak_w: Annotated[float, Field(ge=0.0)]
    observed_wh: Annotated[float, Field(ge=0.0)]
    avoidable_wh: Annotated[float, Field(ge=0.0)]


class DetectorResult(DomainModel):
    kind: FindingKind
    status: DetectionStatus
    confidence: Confidence
    evidence: tuple[RuleEvidence, ...]
    episodes: tuple[Episode, ...] = ()
    summary: str


class PeriodEstimate(DomainModel):
    period: str
    days: Decimal
    energy_kwh: Decimal
    cost: Decimal
    currency: str
    assumptions: tuple[str, ...]

    @field_validator("period")
    @classmethod
    def known_period(cls, value: str) -> str:
        if value not in {"week", "month", "year"}:
            raise ValueError("period must be week, month, or year")
        return value


class SavingsProjection(DomainModel):
    observed_avoidable_kwh: Annotated[Decimal, Field(ge=Decimal("0"))]
    covered_days: Annotated[Decimal, Field(ge=Decimal("0"))]
    estimates: tuple[PeriodEstimate, ...]
    estimate_kind: str
    suppression_reason: str | None = None

    @field_validator("estimate_kind")
    @classmethod
    def known_estimate_kind(cls, value: str) -> str:
        if value not in {"potential", "actionable", "suppressed"}:
            raise ValueError("unknown estimate_kind")
        return value


class VerificationPlan(DomainModel):
    metric: str
    baseline_days: Annotated[int, Field(ge=1)] = 7
    followup_days: Annotated[int, Field(ge=1)] = 7
    success_reduction_percent: Annotated[float, Field(gt=0.0, le=100.0)] = 20.0
    steps: tuple[str, ...]


class Recommendation(DomainModel):
    finding: FindingKind
    action: str
    rationale: str
    safe_to_automate: bool
    verification: VerificationPlan


class AnalysisReport(DomainModel):
    schema_version: str = "1.0"
    generated_at: AwareDatetime
    annotation: DeviceAnnotation
    tariff: TariffPlan
    cadence_seconds: Annotated[float, Field(gt=0.0)]
    coverage: Annotated[float, Field(ge=0.0, le=1.0)]
    results: tuple[DetectorResult, ...]
    savings: SavingsProjection
    recommendations: tuple[Recommendation, ...]
    warnings: tuple[str, ...]
    privacy_notice: str

    def public_dump(self) -> dict[str, Any]:
        """Return the report without accepting or adding source paths or raw readings."""

        return self.model_dump(mode="json")
