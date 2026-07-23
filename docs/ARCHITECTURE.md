# Architecture

WattWraith separates an offline domain core from file, UI, and export adapters. The
same immutable analysis reports drive the CLI, Streamlit interface, static demo, tests,
and release artifacts.

## Dependency direction

```text
adapters/files.py ─┐
                   ├─► services/analysis.py ─► domain/*
cli.py ────────────┤
app.py ────────────┘

domain/* ──► Python, Polars, NumPy/scikit-learn, Pydantic
domain/* ──X file paths, Streamlit state, network, wall clock
```

| Layer | Responsibility | Does not do |
| --- | --- | --- |
| `domain/models.py` | Strict immutable inputs and reports | I/O or UI state |
| `domain/frames.py` | Sort, duplicate handling, cadence, coverage, gap-aware integration | Fill long gaps |
| `domain/segmentation.py` | Seeded log-power KMeans state segmentation | Guess device type |
| `domain/detectors.py` | Four explainable detector computations and evidence | Price energy |
| `domain/savings.py` | Unioned avoidable watts, projection, repricing | Count anomaly spikes as savings |
| `domain/analysis.py` | One-device orchestration and safety recommendations | Read a file |
| `adapters/files.py` | Bounded CSV/JSON/config parsing | Infer units or metadata |
| `services/*` | Multi-device orchestration and exports | Change domain rules |
| `cli.py`, `app.py` | User entry points | Duplicate detection logic |

## Canonical frame

The domain accepts a Polars `DataFrame` with:

```text
timestamp  Datetime[μs, UTC]
device_id  String
watts      Float64
```

Rows are sorted by time. Duplicate device/timestamp readings are averaged and recorded
as a warning. Cadence is the median positive timestamp difference. Intervals longer
than `2.5 × cadence` are excluded from energy integration rather than interpolated.

For a valid adjacent interval, observed energy uses trapezoidal integration:

```text
E_wh = Σ ((P[i] + P[i+1]) / 2) × Δt_seconds / 3600
```

## Deterministic state segmentation

Power is fitted as `log1p(watts)` after clipping only the fit input to the 0.5th and
99.5th percentiles. Candidate KMeans models use 1–4 clusters, `random_state=32`,
`n_init=20`, and a silhouette score penalized for unnecessary states. Original watts,
not clipped values, remain authoritative for integration.

Clusters are ordered by median watts. A low-power state must exceed the configured off
threshold and stay below the user/device standby ceiling before it is eligible as a
standby state.

## Detector contract

Every detector returns:

- kind and one of `detected`, `not_detected`, `insufficient_data`;
- confidence score and component factors;
- machine-readable rule evidence with observed value, operator, threshold, unit, pass
  state, and explanation;
- zero or more bounded episodes;
- a human-readable summary.

Confidence measures rule support and data quality. It is deterministic and bounded
from 0 to 1, but it is not a statistical probability.

### Low-power baseline

Requires a supported low-power cluster above the approved target. Confidence combines
state stability, occupancy, separation, and overall coverage.

### Periodic standby

Uses transitions into the standby state, median interval consistency, MAD ratio,
observed cycle count, and autocorrelation. A constant series cannot be periodic.

### Overnight sustained draw

Converts timestamps back to the annotation's IANA timezone. It groups a cross-midnight
23:00–06:00 window into local nights, requires per-night coverage, then measures the
fraction remaining above the approved target.

### Anomaly spikes

A robust median/MAD deviation supplies explainable candidates. For at least 128 rows,
a seeded IsolationForest confirms candidates using log power, first difference, and
rolling-median residual. Small inputs use the documented robust fallback. Spikes do not
enter the default savings projection because a start-up surge may be legitimate.

## Savings and repricing

Baseline, periodic, and overnight masks may overlap. Per timestamp, the projection uses
the maximum avoidable watts from those masks, not their sum. Only intervals that pass
the same gap rule are integrated.

```text
daily_kWh = observed_avoidable_kWh / covered_days
week      = daily_kWh × 7
month     = daily_kWh × (365.2425 / 12)
year      = daily_kWh × 365.2425
cost      = period_kWh × flat_price_per_kWh
```

Changing the tariff calls `reprice_report`; energy, detector results, evidence, and
confidence stay byte-for-byte equivalent. Fixed fees, taxes, demand charges, tiers,
and seasonal changes are outside v0.1.0.

## Time and randomness

The domain accepts an injectable `Clock`; tests never depend on sleeps or the wall
clock. KMeans, IsolationForest, and fixture generation all use fixed seed `32`.

## Static demo and Pages

GitHub Pages hosts `site/index.html`, generated from the committed synthetic fixture.
It does not attempt to host Streamlit, accept uploads, or include user data. The live
local Streamlit application remains the interactive interface.
