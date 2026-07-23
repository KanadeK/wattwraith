from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest
from pydantic import ValidationError

from wattwraith.domain import (
    AnalysisConfig,
    DetectionStatus,
    DeviceAnnotation,
    FindingKind,
    FrameValidationError,
    PowerReading,
    TariffPlan,
    analyze_device,
    reprice_report,
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 23, 12, tzinfo=UTC)


def _frame(
    powers: list[float],
    *,
    start: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    minutes: int = 5,
    device_id: str = "plug-1",
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [
                start + timedelta(minutes=index * minutes) for index in range(len(powers))
            ],
            "device_id": [device_id] * len(powers),
            "watts": powers,
        },
        schema_overrides={"timestamp": pl.Datetime("us", "UTC")},
    )


def _annotation(**changes: object) -> DeviceAnnotation:
    values: dict[str, object] = {
        "device_id": "plug-1",
        "device_type": "unknown",
        "timezone": "UTC",
        "standby_target_w": 1.0,
    }
    values.update(changes)
    return DeviceAnnotation(**values)


def _tariff(price: str = "0.20") -> TariffPlan:
    return TariffPlan(currency="USD", price_per_kwh=Decimal(price))


def _result(report: object, kind: FindingKind) -> object:
    return next(item for item in report.results if item.kind == kind)  # type: ignore[attr-defined]


def test_models_reject_invalid_power_and_unsafe_essential_shutdown() -> None:
    with pytest.raises(ValidationError):
        PowerReading(timestamp=datetime.now(UTC), device_id="x", watts=-1)
    with pytest.raises(ValidationError):
        PowerReading(timestamp=datetime.now(), device_id="x", watts=1)
    with pytest.raises(ValidationError):
        DeviceAnnotation(device_id="x", essential=True, shutdown_allowed=True)


def test_frame_requires_aware_timestamps_and_one_matching_device() -> None:
    naive = pl.DataFrame(
        {
            "timestamp": [datetime(2026, 1, 1), datetime(2026, 1, 2)],
            "device_id": ["x", "x"],
            "watts": [1.0, 2.0],
        }
    )
    with pytest.raises(FrameValidationError, match="timezone-aware"):
        analyze_device(naive, DeviceAnnotation(device_id="x"), _tariff())
    with pytest.raises(ValueError, match="does not match"):
        analyze_device(_frame([5.0] * 48), DeviceAnnotation(device_id="wrong"), _tariff())


def test_duplicate_timestamps_are_aggregated_and_reported() -> None:
    frame = _frame([4.0] * 600)
    duplicate = pl.concat((frame, frame.slice(0, 1).with_columns(pl.lit(6.0).alias("watts"))))
    report = analyze_device(duplicate, _annotation(), _tariff(), clock=FixedClock())
    assert any("duplicate" in warning.lower() for warning in report.warnings)


def test_all_four_detectors_return_confidence_and_evidence() -> None:
    powers: list[float] = []
    samples_per_day = 24 * 12
    for index in range(7 * samples_per_day):
        minute = (index * 5) % (24 * 60)
        value = 5.0 if minute < 18 * 60 or minute >= 22 * 60 else 70.0
        if index % 72 == 0:
            value = 20.0
        powers.append(value)
    powers[500] = 300.0
    report = analyze_device(
        _frame(powers),
        _annotation(device_type="television", shutdown_allowed=True),
        _tariff(),
        clock=FixedClock(),
    )
    assert {item.kind for item in report.results} == set(FindingKind)
    assert all(item.evidence for item in report.results)
    assert all(0 <= item.confidence.score <= 1 for item in report.results)
    assert _result(report, FindingKind.BASELINE).status == DetectionStatus.DETECTED
    assert _result(report, FindingKind.OVERNIGHT_SUSTAINED).status == DetectionStatus.DETECTED
    assert _result(report, FindingKind.ANOMALY_SPIKE).status == DetectionStatus.DETECTED


def test_periodic_standby_detects_regular_transitions() -> None:
    powers = [2.0] * (7 * 24 * 12)
    for start in range(0, len(powers), 72):
        powers[start : start + 2] = [18.0, 18.0]
    report = analyze_device(_frame(powers), _annotation(), _tariff(), clock=FixedClock())
    periodic = _result(report, FindingKind.PERIODIC_STANDBY)
    assert periodic.status == DetectionStatus.DETECTED
    period = next(item for item in periodic.evidence if item.metric == "period")
    assert period.observed == pytest.approx(6.0)


def test_short_input_is_explicitly_insufficient() -> None:
    report = analyze_device(
        _frame([5.0] * 24),
        _annotation(),
        _tariff(),
        config=AnalysisConfig(min_valid_nights=1),
        clock=FixedClock(),
    )
    assert _result(report, FindingKind.BASELINE).status == DetectionStatus.INSUFFICIENT_DATA


def test_repricing_changes_only_cost_and_tariff() -> None:
    powers = [5.0] * (4 * 24 * 12)
    report = analyze_device(_frame(powers), _annotation(), _tariff(), clock=FixedClock())
    repriced = reprice_report(report, _tariff("0.40"))
    assert repriced.results == report.results
    assert repriced.savings.observed_avoidable_kwh == report.savings.observed_avoidable_kwh
    assert repriced.savings.estimates[0].energy_kwh == report.savings.estimates[0].energy_kwh
    assert repriced.savings.estimates[0].cost == Decimal("0.27")


def test_overlap_is_not_double_counted() -> None:
    powers = [5.0] * (4 * 24 * 12)
    report = analyze_device(_frame(powers), _annotation(), _tariff(), clock=FixedClock())
    # Constant overnight baseline is eligible for both rules; the union remains below
    # the energy of one 4 W load over the measured wall-clock span.
    maximum_kwh = Decimal("4") * Decimal(str((len(powers) - 1) * 5 / 60)) / Decimal("1000")
    assert report.savings.observed_avoidable_kwh <= maximum_kwh.quantize(Decimal("0.001"))


def test_essential_device_suppresses_unapproved_savings_and_automation() -> None:
    report = analyze_device(
        _frame([5.0] * (4 * 24 * 12)),
        _annotation(
            device_type="refrigerator",
            essential=True,
            standby_target_w=None,
        ),
        _tariff(),
        clock=FixedClock(),
    )
    assert report.savings.estimate_kind == "suppressed"
    assert all(not item.safe_to_automate for item in report.recommendations)


def test_fixed_clock_and_public_dump_do_not_add_source_or_identity_inference() -> None:
    report = analyze_device(
        _frame([5.0] * (4 * 24 * 12)),
        _annotation(display_name="Kitchen plug", device_type="unknown"),
        _tariff(),
        clock=FixedClock(),
    )
    payload = report.public_dump()
    text = str(payload).lower()
    assert report.generated_at == datetime(2026, 7, 23, 12, tzinfo=UTC)
    assert "source_path" not in text
    assert "person" not in text
    assert "sleep schedule" not in text
    assert payload["annotation"]["device_type"] == "unknown"


def test_isolation_forest_is_deterministic() -> None:
    powers = [5.0] * 600
    powers[300] = 300.0
    first = analyze_device(_frame(powers), _annotation(), _tariff(), clock=FixedClock())
    second = analyze_device(_frame(powers), _annotation(), _tariff(), clock=FixedClock())
    assert _result(first, FindingKind.ANOMALY_SPIKE) == _result(second, FindingKind.ANOMALY_SPIKE)
