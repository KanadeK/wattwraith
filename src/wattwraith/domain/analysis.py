"""Pure use-case orchestration for one smart-plug device."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import polars as pl

from wattwraith.domain.detectors import (
    DetectorComputation,
    detect_anomaly_spikes,
    detect_baseline,
    detect_overnight_sustained,
    detect_periodic_standby,
)
from wattwraith.domain.frames import validate_and_normalize_frame
from wattwraith.domain.models import (
    AnalysisConfig,
    AnalysisReport,
    DetectionStatus,
    DeviceAnnotation,
    FindingKind,
    Recommendation,
    TariffPlan,
    VerificationPlan,
)
from wattwraith.domain.savings import estimate_savings, reprice_projection
from wattwraith.domain.segmentation import segment_power_states

PRIVACY_NOTICE = (
    "WattWraith analyzes local power measurements only. It does not infer identity, "
    "occupancy, sleep, work schedules, or device type; device metadata is user supplied."
)


class Clock(Protocol):
    def now(self) -> datetime:
        """Return an aware current timestamp."""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _recommendations(
    computations: tuple[DetectorComputation, ...],
    annotation: DeviceAnnotation,
) -> tuple[Recommendation, ...]:
    actions = {
        FindingKind.BASELINE: (
            "measure_low_power_state",
            "Compare standby energy before and after changing the device's own settings.",
            "standby_hours",
        ),
        FindingKind.PERIODIC_STANDBY: (
            "review_periodic_wake",
            "Check documented wake, update, and maintenance settings before changing power.",
            "avoidable_wh_per_day",
        ),
        FindingKind.OVERNIGHT_SUSTAINED: (
            "review_night_schedule",
            "Test a user-approved schedule and compare complete local nights.",
            "night_wh",
        ),
        FindingKind.ANOMALY_SPIKE: (
            "inspect_spike",
            "Inspect the device and plug; isolated peaks are not counted as savings.",
            "avoidable_wh_per_day",
        ),
    }
    recommendations: list[Recommendation] = []
    for computation in computations:
        if computation.result.status != DetectionStatus.DETECTED:
            continue
        action, rationale, metric = actions[computation.result.kind]
        if annotation.essential:
            rationale += " This essential device must not be automatically powered off."
        recommendations.append(
            Recommendation(
                finding=computation.result.kind,
                action=action,
                rationale=rationale,
                safe_to_automate=(
                    annotation.shutdown_allowed
                    and not annotation.essential
                    and computation.result.kind != FindingKind.ANOMALY_SPIKE
                ),
                verification=VerificationPlan(
                    metric=metric,
                    steps=(
                        "Record seven covered baseline days.",
                        "Apply one reversible, manufacturer-supported change.",
                        "Record seven covered follow-up days and compare the same metric.",
                    ),
                ),
            )
        )
    return tuple(recommendations)


def analyze_device(
    frame: pl.DataFrame,
    annotation: DeviceAnnotation,
    tariff: TariffPlan,
    *,
    config: AnalysisConfig | None = None,
    clock: Clock | None = None,
) -> AnalysisReport:
    """Analyze one device without file, UI, network, or wall-clock coupling."""

    effective_config = config or AnalysisConfig()
    effective_clock = clock or SystemClock()
    normalized = validate_and_normalize_frame(frame, config=effective_config)
    observed_device = str(normalized.frame.item(0, "device_id"))
    if observed_device != annotation.device_id:
        raise ValueError(
            f"annotation device_id {annotation.device_id!r} does not match "
            f"frame device_id {observed_device!r}"
        )

    segmentation = segment_power_states(
        normalized.frame,
        annotation=annotation,
        config=effective_config,
    )
    target = (
        annotation.standby_target_w
        if annotation.standby_target_w is not None
        else effective_config.off_threshold_w
    )
    computations = (
        detect_baseline(
            normalized.frame,
            segmentation,
            target_w=target,
            cadence_seconds=normalized.cadence_seconds,
            coverage=normalized.coverage,
            config=effective_config,
        ),
        detect_periodic_standby(
            normalized.frame,
            segmentation,
            target_w=target,
            cadence_seconds=normalized.cadence_seconds,
            coverage=normalized.coverage,
            config=effective_config,
        ),
        detect_overnight_sustained(
            normalized.frame,
            annotation,
            target_w=target,
            cadence_seconds=normalized.cadence_seconds,
            config=effective_config,
        ),
        detect_anomaly_spikes(
            normalized.frame,
            target_w=target,
            cadence_seconds=normalized.cadence_seconds,
            coverage=normalized.coverage,
            config=effective_config,
        ),
    )
    savings = estimate_savings(
        normalized.frame,
        computations,
        annotation,
        tariff,
        cadence_seconds=normalized.cadence_seconds,
        coverage=normalized.coverage,
        config=effective_config,
    )
    return AnalysisReport(
        generated_at=effective_clock.now(),
        annotation=annotation,
        tariff=tariff,
        cadence_seconds=normalized.cadence_seconds,
        coverage=normalized.coverage,
        results=tuple(computation.result for computation in computations),
        savings=savings,
        recommendations=_recommendations(computations, annotation),
        warnings=normalized.warnings,
        privacy_notice=PRIVACY_NOTICE,
    )


def reprice_report(report: AnalysisReport, tariff: TariffPlan) -> AnalysisReport:
    """Reprice a report while preserving every energy and detector field."""

    return report.model_copy(
        update={
            "tariff": tariff,
            "savings": reprice_projection(report.savings, tariff),
        }
    )
