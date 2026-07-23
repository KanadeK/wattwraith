"""Gap-aware, overlap-safe energy projections and tariff repricing."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import polars as pl

from wattwraith.domain.detectors import DetectorComputation
from wattwraith.domain.frames import gap_aware_energy_wh
from wattwraith.domain.models import (
    AnalysisConfig,
    DetectionStatus,
    DeviceAnnotation,
    FindingKind,
    PeriodEstimate,
    SavingsProjection,
    TariffPlan,
)

_PERIOD_DAYS = {
    "week": Decimal("7"),
    "month": Decimal("30.436875"),
    "year": Decimal("365.2425"),
}
_ENERGY_QUANTUM = Decimal("0.001")
_MONEY_QUANTUM = Decimal("0.01")


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _period_estimates(
    daily_kwh: Decimal,
    tariff: TariffPlan,
) -> tuple[PeriodEstimate, ...]:
    assumptions = (
        "Observed avoidable energy is extrapolated linearly.",
        "Fixed charges, taxes, tiers, and seasonal changes are excluded.",
    )
    return tuple(
        PeriodEstimate(
            period=period,
            days=days,
            energy_kwh=(daily_kwh * days).quantize(_ENERGY_QUANTUM, ROUND_HALF_UP),
            cost=(daily_kwh * days * tariff.price_per_kwh).quantize(
                _MONEY_QUANTUM, ROUND_HALF_UP
            ),
            currency=tariff.currency,
            assumptions=assumptions,
        )
        for period, days in _PERIOD_DAYS.items()
    )


def estimate_savings(
    frame: pl.DataFrame,
    computations: tuple[DetectorComputation, ...],
    annotation: DeviceAnnotation,
    tariff: TariffPlan,
    *,
    cadence_seconds: float,
    coverage: float,
    config: AnalysisConfig,
) -> SavingsProjection:
    """Project the union of avoidable masks, never the sum of overlapping rules."""

    timestamps = frame.get_column("timestamp").to_list()
    watts = [float(value) for value in frame.get_column("watts").to_list()]
    target = annotation.standby_target_w
    if annotation.essential and target is None:
        return SavingsProjection(
            observed_avoidable_kwh=Decimal("0"),
            covered_days=Decimal("0"),
            estimates=(),
            estimate_kind="suppressed",
            suppression_reason=(
                "Essential device has no user-supplied safe standby target."
            ),
        )

    effective_target = target if target is not None else config.off_threshold_w
    included = [
        computation
        for computation in computations
        if computation.result.status == DetectionStatus.DETECTED
        and computation.result.kind != FindingKind.ANOMALY_SPIKE
    ]
    union_mask = [
        any(computation.mask[index] for computation in included)
        for index in range(frame.height)
    ]
    avoidable_w = [
        max(0.0, value - effective_target) if union_mask[index] else 0.0
        for index, value in enumerate(watts)
    ]
    energy_wh, valid_seconds = gap_aware_energy_wh(
        timestamps,
        avoidable_w,
        cadence_seconds=cadence_seconds,
        max_gap_factor=config.max_gap_factor,
    )
    covered_days = valid_seconds / 86400
    observed_kwh = _decimal(energy_wh / 1000).quantize(_ENERGY_QUANTUM, ROUND_HALF_UP)
    if coverage < config.minimum_coverage or covered_days < 2:
        return SavingsProjection(
            observed_avoidable_kwh=observed_kwh,
            covered_days=_decimal(covered_days).quantize(
                Decimal("0.001"), ROUND_HALF_UP
            ),
            estimates=(),
            estimate_kind="suppressed",
            suppression_reason="At least two covered days and 75% coverage are required.",
        )
    daily_kwh = _decimal(energy_wh / 1000 / covered_days)
    kind = "actionable" if annotation.shutdown_allowed or target is not None else "potential"
    return SavingsProjection(
        observed_avoidable_kwh=observed_kwh,
        covered_days=_decimal(covered_days).quantize(Decimal("0.001"), ROUND_HALF_UP),
        estimates=_period_estimates(daily_kwh, tariff),
        estimate_kind=kind,
    )


def reprice_projection(
    projection: SavingsProjection,
    tariff: TariffPlan,
) -> SavingsProjection:
    """Change only monetary fields; energy and detection never rerun."""

    estimates = tuple(
        estimate.model_copy(
            update={
                "cost": (estimate.energy_kwh * tariff.price_per_kwh).quantize(
                    _MONEY_QUANTUM, ROUND_HALF_UP
                ),
                "currency": tariff.currency,
            }
        )
        for estimate in projection.estimates
    )
    return projection.model_copy(update={"estimates": estimates})
