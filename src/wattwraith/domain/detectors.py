"""Explainable deterministic detectors for phantom-load patterns."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from math import log1p, sqrt
from statistics import median
from zoneinfo import ZoneInfo

import polars as pl
from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]

from wattwraith.domain.models import (
    AnalysisConfig,
    Confidence,
    ConfidenceGrade,
    DetectionStatus,
    DetectorResult,
    DeviceAnnotation,
    Episode,
    FindingKind,
    RuleEvidence,
)
from wattwraith.domain.segmentation import StateSegmentation


@dataclass(frozen=True)
class DetectorComputation:
    result: DetectorResult
    mask: tuple[bool, ...]


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _confidence(score: float, factors: dict[str, float], cap: float = 1.0) -> Confidence:
    score = min(cap, _clip(score))
    if score >= 0.80:
        grade = ConfidenceGrade.HIGH
    elif score >= 0.55:
        grade = ConfidenceGrade.MEDIUM
    else:
        grade = ConfidenceGrade.LOW
    return Confidence(
        score=score,
        grade=grade,
        factors={key: _clip(value) for key, value in factors.items()},
    )


def _empty(
    kind: FindingKind,
    status: DetectionStatus,
    summary: str,
    evidence: list[RuleEvidence],
    size: int,
    *,
    confidence: float = 0.0,
) -> DetectorComputation:
    return DetectorComputation(
        DetectorResult(
            kind=kind,
            status=status,
            confidence=_confidence(confidence, {"evidence_strength": confidence}),
            evidence=tuple(evidence),
            summary=summary,
        ),
        (False,) * size,
    )


def _mad(values: list[float]) -> float:
    center = median(values)
    return float(median(abs(value - center) for value in values))


def _correlation(values: list[int], lag: int) -> float:
    if lag <= 0 or lag >= len(values):
        return 0.0
    left = values[:-lag]
    right = values[lag:]
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True)
    )
    left_sum = sum((value - left_mean) ** 2 for value in left)
    right_sum = sum((value - right_mean) ** 2 for value in right)
    denominator = sqrt(left_sum * right_sum)
    return numerator / denominator if denominator else 0.0


def _episodes(
    frame: pl.DataFrame,
    mask: tuple[bool, ...],
    *,
    target_w: float,
    cadence_seconds: float,
) -> tuple[Episode, ...]:
    timestamps: list[datetime] = frame.get_column("timestamp").to_list()
    watts = [float(value) for value in frame.get_column("watts").to_list()]
    groups: list[list[int]] = []
    for index, flagged in enumerate(mask):
        if not flagged:
            continue
        if (
            not groups
            or index != groups[-1][-1] + 1
            or (timestamps[index] - timestamps[groups[-1][-1]]).total_seconds()
            > cadence_seconds * 2.5
        ):
            groups.append([index])
        else:
            groups[-1].append(index)
    return tuple(
        Episode(
            start=timestamps[group[0]],
            end=timestamps[group[-1]] + timedelta(seconds=cadence_seconds),
            peak_w=max(watts[index] for index in group),
            observed_wh=sum(watts[index] for index in group) * cadence_seconds / 3600,
            avoidable_wh=sum(max(0.0, watts[index] - target_w) for index in group)
            * cadence_seconds
            / 3600,
        )
        for group in groups
    )


def detect_baseline(
    frame: pl.DataFrame,
    segmentation: StateSegmentation,
    *,
    target_w: float,
    cadence_seconds: float,
    coverage: float,
    config: AnalysisConfig,
) -> DetectorComputation:
    size = frame.height
    sample_passed = size >= config.min_baseline_samples
    evidence = [
        RuleEvidence(
            rule_id="baseline.low_state.v1",
            metric="sample_count",
            observed=size,
            operator=">=",
            threshold=config.min_baseline_samples,
            unit="samples",
            passed=sample_passed,
            explanation="A stable baseline needs enough observations.",
        )
    ]
    if not sample_passed:
        return _empty(
            FindingKind.BASELINE,
            DetectionStatus.INSUFFICIENT_DATA,
            "Not enough readings to estimate a baseline.",
            evidence,
            size,
        )
    if segmentation.standby_state is None:
        evidence.append(
            RuleEvidence(
                rule_id="baseline.low_state.v1",
                metric="standby_state",
                observed="none",
                operator="==",
                threshold="present",
                passed=False,
                explanation="No low non-off state was separated from active power.",
            )
        )
        return _empty(
            FindingKind.BASELINE,
            DetectionStatus.NOT_DETECTED,
            "No qualifying low-power baseline was found.",
            evidence,
            size,
            confidence=coverage * 0.6,
        )

    state = segmentation.states[segmentation.standby_state]
    occupancy_passed = state.occupancy >= 0.05
    evidence.extend(
        (
            RuleEvidence(
                rule_id="baseline.low_state.v1",
                metric="baseline_power",
                observed=round(state.median_w, 6),
                operator=">",
                threshold=config.off_threshold_w,
                unit="W",
                passed=state.median_w > config.off_threshold_w,
                explanation="The candidate is above the configured off threshold.",
            ),
            RuleEvidence(
                rule_id="baseline.low_state.v1",
                metric="state_occupancy",
                observed=round(state.occupancy, 6),
                operator=">=",
                threshold=0.05,
                unit="fraction",
                passed=occupancy_passed,
                explanation="The low state must occupy at least 5% of readings.",
            ),
        )
    )
    detected = state.median_w > config.off_threshold_w and occupancy_passed
    if not detected:
        return _empty(
            FindingKind.BASELINE,
            DetectionStatus.NOT_DETECTED,
            "The low-power state did not meet baseline rules.",
            evidence,
            size,
            confidence=coverage * 0.5,
        )
    mask = tuple(label == segmentation.standby_state for label in segmentation.labels)
    stability = 1.0 - min(
        1.0, (1.4826 * state.mad_w) / (0.25 * max(state.median_w, 1.0))
    )
    support = min(1.0, state.occupancy / 0.20)
    score = 0.35 * stability + 0.25 * support + 0.25 * segmentation.confidence + 0.15 * coverage
    confidence = _confidence(
        score,
        {
            "stability": stability,
            "support": support,
            "state_separation": segmentation.confidence,
            "coverage": coverage,
        },
        cap=0.70 if len(segmentation.states) == 1 else 1.0,
    )
    return DetectorComputation(
        DetectorResult(
            kind=FindingKind.BASELINE,
            status=DetectionStatus.DETECTED,
            confidence=confidence,
            evidence=tuple(evidence),
            episodes=_episodes(
                frame, mask, target_w=target_w, cadence_seconds=cadence_seconds
            ),
            summary=f"Stable low-power state near {state.median_w:.2f} W.",
        ),
        mask,
    )


def detect_periodic_standby(
    frame: pl.DataFrame,
    segmentation: StateSegmentation,
    *,
    target_w: float,
    cadence_seconds: float,
    coverage: float,
    config: AnalysisConfig,
) -> DetectorComputation:
    size = frame.height
    if segmentation.standby_state is None:
        return _empty(
            FindingKind.PERIODIC_STANDBY,
            DetectionStatus.NOT_DETECTED,
            "No standby state exists for periodic analysis.",
            [
                RuleEvidence(
                    rule_id="periodic.transitions_autocorr.v1",
                    metric="standby_state",
                    observed="none",
                    operator="==",
                    threshold="present",
                    passed=False,
                    explanation="Transitions require a detected standby state.",
                )
            ],
            size,
            confidence=coverage * 0.5,
        )
    binary = [int(label == segmentation.standby_state) for label in segmentation.labels]
    timestamps: list[datetime] = frame.get_column("timestamp").to_list()
    transitions = [
        timestamps[index]
        for index in range(1, size)
        if binary[index - 1] == 1 and binary[index] == 0
    ]
    minimum_transitions = config.min_period_cycles + 1
    evidence = [
        RuleEvidence(
            rule_id="periodic.transitions_autocorr.v1",
            metric="transition_count",
            observed=len(transitions),
            operator=">=",
            threshold=minimum_transitions,
            unit="events",
            passed=len(transitions) >= minimum_transitions,
            explanation="At least three repeated intervals are required.",
        )
    ]
    if len(transitions) < minimum_transitions:
        return _empty(
            FindingKind.PERIODIC_STANDBY,
            DetectionStatus.NOT_DETECTED,
            "Standby transitions were not repeated often enough.",
            evidence,
            size,
            confidence=coverage * 0.6,
        )

    intervals = [
        (right - left).total_seconds()
        for left, right in pairwise(transitions)
    ]
    period_seconds = float(median(intervals))
    mad_ratio = _mad(intervals) / period_seconds if period_seconds else 1.0
    lag = max(1, round(period_seconds / cadence_seconds))
    correlation = _correlation(binary, lag)
    in_range = (
        config.min_period_minutes * 60
        <= period_seconds
        <= config.max_period_hours * 3600
    )
    consistent = mad_ratio <= config.periodic_interval_mad_ratio
    correlated = correlation >= config.periodic_autocorrelation_threshold
    evidence.extend(
        (
            RuleEvidence(
                rule_id="periodic.transitions_autocorr.v1",
                metric="period",
                observed=round(period_seconds / 3600, 6),
                operator="between",
                threshold=(
                    f"{config.min_period_minutes / 60:g}..{config.max_period_hours:g}"
                ),
                unit="hours",
                passed=in_range,
                explanation="The candidate period must be in the configured range.",
            ),
            RuleEvidence(
                rule_id="periodic.transitions_autocorr.v1",
                metric="interval_mad_ratio",
                observed=round(mad_ratio, 6),
                operator="<=",
                threshold=config.periodic_interval_mad_ratio,
                passed=consistent,
                explanation="Transition intervals must be repeatable.",
            ),
            RuleEvidence(
                rule_id="periodic.transitions_autocorr.v1",
                metric="autocorrelation",
                observed=round(correlation, 6),
                operator=">=",
                threshold=config.periodic_autocorrelation_threshold,
                passed=correlated,
                explanation="Autocorrelation confirms the transition period.",
            ),
        )
    )
    if not (in_range and consistent and correlated):
        return _empty(
            FindingKind.PERIODIC_STANDBY,
            DetectionStatus.NOT_DETECTED,
            "Repeated transitions did not satisfy the periodicity rules.",
            evidence,
            size,
            confidence=coverage * 0.65,
        )
    cycle_support = min(1.0, (len(transitions) - 1) / 6)
    corr_strength = _clip((correlation - 0.35) / 0.65)
    interval_consistency = 1.0 - min(
        1.0, mad_ratio / config.periodic_interval_mad_ratio
    )
    score = (
        0.40 * corr_strength
        + 0.20 * cycle_support
        + 0.20 * interval_consistency
        + 0.15 * coverage
        + 0.05 * segmentation.confidence
    )
    mask = tuple(bool(value) for value in binary)
    return DetectorComputation(
        DetectorResult(
            kind=FindingKind.PERIODIC_STANDBY,
            status=DetectionStatus.DETECTED,
            confidence=_confidence(
                score,
                {
                    "autocorrelation": corr_strength,
                    "cycle_support": cycle_support,
                    "interval_consistency": interval_consistency,
                    "coverage": coverage,
                },
            ),
            evidence=tuple(evidence),
            episodes=_episodes(
                frame, mask, target_w=target_w, cadence_seconds=cadence_seconds
            ),
            summary=f"Standby transitions repeat about every {period_seconds / 3600:.2f} h.",
        ),
        mask,
    )


def _night_key(
    timestamp: datetime, annotation: DeviceAnnotation
) -> tuple[date, datetime, datetime] | None:
    zone = ZoneInfo(annotation.timezone)
    local = timestamp.astimezone(zone)
    window = annotation.night_window
    wraps = window.start > window.end
    if wraps:
        if local.time() >= window.start:
            key = local.date()
        elif local.time() < window.end:
            key = local.date() - timedelta(days=1)
        else:
            return None
        end_date = key + timedelta(days=1)
    else:
        if not window.start <= local.time() < window.end:
            return None
        key = local.date()
        end_date = key
    start = datetime.combine(key, window.start, zone).astimezone(UTC)
    end = datetime.combine(end_date, window.end, zone).astimezone(UTC)
    return key, start, end


def detect_overnight_sustained(
    frame: pl.DataFrame,
    annotation: DeviceAnnotation,
    *,
    target_w: float,
    cadence_seconds: float,
    config: AnalysisConfig,
) -> DetectorComputation:
    timestamps: list[datetime] = frame.get_column("timestamp").to_list()
    watts = [float(value) for value in frame.get_column("watts").to_list()]
    grouped: dict[date, tuple[datetime, datetime, list[int]]] = {}
    for index, timestamp in enumerate(timestamps):
        keyed = _night_key(timestamp, annotation)
        if keyed is None:
            continue
        key, start, end = keyed
        grouped.setdefault(key, (start, end, []))[2].append(index)

    threshold_w = max(config.night_min_w, target_w + 1.0)
    valid: list[tuple[date, float, float, list[int]]] = []
    for key, (start, end, indexes) in grouped.items():
        expected_seconds = (end - start).total_seconds()
        coverage = min(1.0, len(indexes) * cadence_seconds / expected_seconds)
        fraction = sum(watts[index] >= threshold_w for index in indexes) / len(indexes)
        if coverage >= config.night_min_coverage:
            valid.append((key, coverage, fraction, indexes))
    pass_count = sum(fraction >= config.night_sustained_fraction for _, _, fraction, _ in valid)
    pass_rate = pass_count / len(valid) if valid else 0.0
    median_fraction = float(median(item[2] for item in valid)) if valid else 0.0
    evidence = [
        RuleEvidence(
            rule_id="overnight.local_window_sustained.v1",
            metric="valid_nights",
            observed=len(valid),
            operator=">=",
            threshold=config.min_valid_nights,
            unit="nights",
            passed=len(valid) >= config.min_valid_nights,
            explanation="Partial nights are excluded using local-time coverage.",
        ),
        RuleEvidence(
            rule_id="overnight.local_window_sustained.v1",
            metric="night_pass_rate",
            observed=round(pass_rate, 6),
            operator=">=",
            threshold=config.night_pass_rate,
            passed=pass_rate >= config.night_pass_rate,
            explanation="Enough valid nights must sustain power above the threshold.",
        ),
        RuleEvidence(
            rule_id="overnight.local_window_sustained.v1",
            metric="median_sustained_fraction",
            observed=round(median_fraction, 6),
            operator=">=",
            threshold=config.night_sustained_fraction,
            passed=median_fraction >= config.night_sustained_fraction,
            explanation=f"Night readings are tested against {threshold_w:.2f} W.",
        ),
    ]
    if len(valid) < config.min_valid_nights:
        return _empty(
            FindingKind.OVERNIGHT_SUSTAINED,
            DetectionStatus.INSUFFICIENT_DATA,
            "Not enough complete local nights were observed.",
            evidence,
            frame.height,
        )
    detected = (
        pass_rate >= config.night_pass_rate
        and median_fraction >= config.night_sustained_fraction
    )
    if not detected:
        return _empty(
            FindingKind.OVERNIGHT_SUSTAINED,
            DetectionStatus.NOT_DETECTED,
            "Power was not sustained across enough complete nights.",
            evidence,
            frame.height,
            confidence=sum(item[1] for item in valid) / len(valid) * 0.7,
        )
    qualifying_indexes = {
        index
        for _, _, fraction, indexes in valid
        if fraction >= config.night_sustained_fraction
        for index in indexes
        if watts[index] >= threshold_w
    }
    mask = tuple(index in qualifying_indexes for index in range(frame.height))
    median_coverage = float(median(item[1] for item in valid))
    night_support = min(1.0, len(valid) / 7)
    score = (
        0.30 * median_coverage
        + 0.30 * pass_rate
        + 0.25 * median_fraction
        + 0.15 * night_support
    )
    return DetectorComputation(
        DetectorResult(
            kind=FindingKind.OVERNIGHT_SUSTAINED,
            status=DetectionStatus.DETECTED,
            confidence=_confidence(
                score,
                {
                    "night_coverage": median_coverage,
                    "pass_rate": pass_rate,
                    "sustained_fraction": median_fraction,
                    "night_support": night_support,
                },
            ),
            evidence=tuple(evidence),
            episodes=_episodes(
                frame, mask, target_w=target_w, cadence_seconds=cadence_seconds
            ),
            summary=f"Sustained draw above {threshold_w:.2f} W occurs overnight.",
        ),
        mask,
    )


def detect_anomaly_spikes(
    frame: pl.DataFrame,
    *,
    target_w: float,
    cadence_seconds: float,
    coverage: float,
    config: AnalysisConfig,
) -> DetectorComputation:
    watts = [float(value) for value in frame.get_column("watts").to_list()]
    window = max(3, round(3600 / cadence_seconds))
    if window % 2 == 0:
        window += 1
    half = window // 2
    rolling = [
        float(median(watts[max(0, index - half) : min(len(watts), index + half + 1)]))
        for index in range(len(watts))
    ]
    residual = [max(0.0, value - center) for value, center in zip(watts, rolling, strict=True)]
    residual_center = float(median(residual))
    residual_sigma = max(1.4826 * _mad(residual), 0.1)
    robust_z = [(value - residual_center) / residual_sigma for value in residual]
    robust_candidates = [
        score >= config.spike_robust_z
        and residual[index] >= max(10.0, 0.5 * max(rolling[index], 1.0))
        for index, score in enumerate(robust_z)
    ]

    used_isolation_forest = len(watts) >= 128
    if used_isolation_forest:
        global_sigma = max(1.4826 * _mad(watts), 0.1)
        features = [
            [
                log1p(value),
                (value - (watts[index - 1] if index else value)) / global_sigma,
                residual[index] / residual_sigma,
            ]
            for index, value in enumerate(watts)
        ]
        model = IsolationForest(
            n_estimators=128,
            contamination=config.isolation_contamination,
            random_state=config.random_seed,
            n_jobs=1,
        )
        model.fit(features)
        model_flags = [score < 0.0 for score in model.decision_function(features).tolist()]
        mask = tuple(
            robust and model_flag
            for robust, model_flag in zip(robust_candidates, model_flags, strict=True)
        )
    else:
        mask = tuple(robust_candidates)

    count = sum(mask)
    evidence = [
        RuleEvidence(
            rule_id="spike.robust_iforest.v1",
            metric="spike_count",
            observed=count,
            operator=">=",
            threshold=1,
            unit="samples",
            passed=count > 0,
            explanation="A spike must exceed robust local residual thresholds.",
        ),
        RuleEvidence(
            rule_id="spike.robust_iforest.v1",
            metric="isolation_forest",
            observed="used" if used_isolation_forest else "small-sample fallback",
            operator="==",
            threshold="used when samples >= 128",
            passed=used_isolation_forest,
            explanation="The fallback remains deterministic but has capped confidence.",
        ),
    ]
    if not count:
        return _empty(
            FindingKind.ANOMALY_SPIKE,
            DetectionStatus.NOT_DETECTED,
            "No isolated power spike met the robust rule.",
            evidence,
            len(watts),
            confidence=coverage * 0.7,
        )
    maximum_strength = min(
        1.0,
        max(robust_z[index] for index, flagged in enumerate(mask) if flagged)
        / (config.spike_robust_z * 2),
    )
    score = 0.55 * maximum_strength + 0.25 * coverage + 0.20 * used_isolation_forest
    return DetectorComputation(
        DetectorResult(
            kind=FindingKind.ANOMALY_SPIKE,
            status=DetectionStatus.DETECTED,
            confidence=_confidence(
                score,
                {
                    "robust_strength": maximum_strength,
                    "coverage": coverage,
                    "model_confirmation": float(used_isolation_forest),
                },
                cap=1.0 if used_isolation_forest else 0.65,
            ),
            evidence=tuple(evidence),
            episodes=_episodes(
                frame, mask, target_w=target_w, cadence_seconds=cadence_seconds
            ),
            summary=f"Detected {count} isolated high-power sample(s).",
        ),
        mask,
    )
