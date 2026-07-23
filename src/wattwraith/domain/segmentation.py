"""Deterministic low-power state segmentation."""

from __future__ import annotations

from dataclasses import dataclass
from math import log1p
from statistics import median

import polars as pl
from sklearn.cluster import KMeans  # type: ignore[import-untyped]
from sklearn.metrics import silhouette_score  # type: ignore[import-untyped]

from wattwraith.domain.models import AnalysisConfig, DeviceAnnotation


@dataclass(frozen=True)
class PowerState:
    index: int
    median_w: float
    occupancy: float
    mad_w: float
    label: str


@dataclass(frozen=True)
class StateSegmentation:
    labels: tuple[int, ...]
    states: tuple[PowerState, ...]
    standby_state: int | None
    confidence: float


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _mad(values: list[float]) -> float:
    center = median(values)
    return float(median(abs(value - center) for value in values))


def _training_rows(rows: list[list[float]], limit: int = 5_000) -> list[list[float]]:
    if len(rows) <= limit:
        return rows
    return [rows[index * (len(rows) - 1) // (limit - 1)] for index in range(limit)]


def segment_power_states(
    frame: pl.DataFrame,
    *,
    annotation: DeviceAnnotation,
    config: AnalysisConfig,
) -> StateSegmentation:
    """Cluster log power, choosing a compact model with deterministic scoring."""

    watts = [float(value) for value in frame.get_column("watts").to_list()]
    lower = _quantile(watts, 0.005)
    upper = _quantile(watts, 0.995)
    rows = [[log1p(min(upper, max(lower, value)))] for value in watts]
    training = _training_rows(rows)
    distinct = len({round(row[0], 12) for row in training})
    minimum_cluster = max(3, int(len(training) * config.min_state_fraction))
    max_k = min(4, distinct, max(1, len(training) // minimum_cluster))

    best_model: KMeans | None = None
    best_score = float("-inf")
    for cluster_count in range(2, max_k + 1):
        model = KMeans(
            n_clusters=cluster_count,
            random_state=config.random_seed,
            n_init=20,
            algorithm="lloyd",
        )
        labels = model.fit_predict(training)
        counts = [labels.tolist().count(index) for index in range(cluster_count)]
        if min(counts) < minimum_cluster:
            continue
        score = float(silhouette_score(training, labels)) - 0.02 * (cluster_count - 1)
        if score > best_score:
            best_model = model
            best_score = score

    if best_model is None or best_score < 0.25:
        raw_labels = [0] * len(watts)
    else:
        raw_labels = [int(value) for value in best_model.predict(rows).tolist()]

    raw_indexes = sorted(set(raw_labels))
    raw_groups = {
        index: [watts[position] for position, label in enumerate(raw_labels) if label == index]
        for index in raw_indexes
    }
    ordered_raw = sorted(raw_indexes, key=lambda index: median(raw_groups[index]))
    remap = {raw: ordered for ordered, raw in enumerate(ordered_raw)}
    labels = tuple(remap[label] for label in raw_labels)

    maximum_standby = annotation.standby_max_w or config.standby_max_w
    states: list[PowerState] = []
    for ordered_index, raw_index in enumerate(ordered_raw):
        group = raw_groups[raw_index]
        center = float(median(group))
        if center <= config.off_threshold_w:
            state_label = "off"
        elif center <= maximum_standby and not any(state.label == "standby" for state in states):
            state_label = "standby"
        else:
            state_label = "active"
        states.append(
            PowerState(
                index=ordered_index,
                median_w=center,
                occupancy=len(group) / len(watts),
                mad_w=_mad(group),
                label=state_label,
            )
        )

    standby = next((state.index for state in states if state.label == "standby"), None)
    if standby is None:
        confidence = 0.0
    else:
        state = states[standby]
        stability = 1.0 - min(
            1.0,
            (1.4826 * state.mad_w) / (0.25 * max(state.median_w, 1.0)),
        )
        support = min(1.0, state.occupancy / 0.20)
        neighbors = [
            abs(log1p(other.median_w) - log1p(state.median_w))
            for other in states
            if other.index != state.index
        ]
        separation = min(1.0, min(neighbors)) if neighbors else 0.5
        confidence = 0.4 * stability + 0.3 * support + 0.3 * separation
        if len(states) == 1:
            confidence = min(confidence, 0.70)

    return StateSegmentation(labels, tuple(states), standby, max(0.0, min(1.0, confidence)))
