from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest

from wattwraith.domain import (
    AnalysisConfig,
    DeviceAnnotation,
    FrameValidationError,
    TariffPlan,
    analyze_device,
    reprice_report,
)
from wattwraith.domain.frames import gap_aware_energy_wh, validate_and_normalize_frame


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 23, 12, tzinfo=UTC)


def _frame(
    powers: list[float],
    *,
    device_ids: list[str] | None = None,
    timestamps: list[datetime] | None = None,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": timestamps
            or [
                datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=5 * index)
                for index in range(len(powers))
            ],
            "device_id": device_ids or ["plug-1"] * len(powers),
            "watts": powers,
        },
        schema_overrides={"timestamp": pl.Datetime("us", "UTC")},
    )


@pytest.mark.parametrize(
    ("frame", "config", "message"),
    [
        (_frame([]), AnalysisConfig(), "at least two readings"),
        (_frame([1.0, 1.0, 1.0]), AnalysisConfig(max_rows=2), "row safety limit"),
        (
            _frame([1.0, 1.0], device_ids=["one", "two"]),
            AnalysisConfig(),
            "exactly one device_id",
        ),
        (_frame([1.0, float("nan")]), AnalysisConfig(), "finite"),
        (_frame([1.0, 100_001.0]), AnalysisConfig(), "between 0 and 100000"),
    ],
)
def test_frame_validation_failure_branches(
    frame: pl.DataFrame,
    config: AnalysisConfig,
    message: str,
) -> None:
    with pytest.raises(FrameValidationError, match=message):
        validate_and_normalize_frame(frame, config=config)


def test_duplicates_are_averaged_and_large_gaps_reduce_coverage() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    frame = _frame(
        [1.0, 3.0, 5.0, 1.0, 1.0],
        timestamps=[
            start,
            start + timedelta(minutes=5),
            start + timedelta(minutes=5),
            start + timedelta(minutes=10),
            start + timedelta(minutes=60),
        ],
    )
    normalized = validate_and_normalize_frame(frame, config=AnalysisConfig())

    assert normalized.frame.height == 4
    assert normalized.frame.item(1, "watts") == pytest.approx(4.0)
    assert normalized.cadence_seconds == pytest.approx(300.0)
    assert normalized.coverage == pytest.approx(1 / 6)
    assert any("duplicate" in warning.lower() for warning in normalized.warnings)
    assert any("exceeds 1%" in warning for warning in normalized.warnings)


def test_irregular_cadence_uses_median_positive_delta() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    normalized = validate_and_normalize_frame(
        _frame(
            [1.0, 2.0, 1.0, 2.0],
            timestamps=[
                start,
                start + timedelta(minutes=5),
                start + timedelta(minutes=15),
                start + timedelta(minutes=20),
            ],
        ),
        config=AnalysisConfig(),
    )
    assert normalized.cadence_seconds == pytest.approx(300.0)
    assert normalized.coverage == pytest.approx(1.0)


def test_gap_aware_energy_does_not_bridge_missing_data() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    energy_wh, valid_seconds = gap_aware_energy_wh(
        [start, start + timedelta(minutes=5), start + timedelta(minutes=65)],
        [10.0, 10.0, 10.0],
        cadence_seconds=300.0,
        max_gap_factor=2.5,
    )
    assert energy_wh == pytest.approx(10.0 * 5 / 60)
    assert valid_seconds == pytest.approx(300.0)


def test_essential_device_with_explicit_target_still_blocks_automation() -> None:
    report = analyze_device(
        _frame([5.0] * (4 * 24 * 12)),
        DeviceAnnotation(
            device_id="plug-1",
            device_type="refrigerator",
            essential=True,
            standby_target_w=1.0,
        ),
        TariffPlan(currency="USD", price_per_kwh=Decimal("0.20")),
        clock=FixedClock(),
    )
    assert report.recommendations
    assert all(not recommendation.safe_to_automate for recommendation in report.recommendations)
    assert all(
        "essential device" in recommendation.rationale.lower()
        for recommendation in report.recommendations
    )


def test_repricing_is_deterministic_and_changes_only_money() -> None:
    tariff = TariffPlan(currency="USD", price_per_kwh=Decimal("0.20"))
    report = analyze_device(
        _frame([5.0] * (4 * 24 * 12)),
        DeviceAnnotation(
            device_id="plug-1",
            standby_target_w=1.0,
            shutdown_allowed=True,
        ),
        tariff,
        clock=FixedClock(),
    )
    repeated = analyze_device(
        _frame([5.0] * (4 * 24 * 12)),
        report.annotation,
        tariff,
        clock=FixedClock(),
    )
    repriced = reprice_report(
        report,
        TariffPlan(currency="EUR", price_per_kwh=Decimal("0.40")),
    )

    assert repeated == report
    assert repriced.results == report.results
    assert repriced.recommendations == report.recommendations
    assert repriced.generated_at == report.generated_at
    assert repriced.coverage == report.coverage
    assert repriced.savings.observed_avoidable_kwh == report.savings.observed_avoidable_kwh
    assert [item.energy_kwh for item in repriced.savings.estimates] == [
        item.energy_kwh for item in report.savings.estimates
    ]
    assert [item.cost for item in repriced.savings.estimates] != [
        item.cost for item in report.savings.estimates
    ]
    assert {item.currency for item in repriced.savings.estimates} == {"EUR"}
