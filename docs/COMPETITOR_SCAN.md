# Public repository sample scan

Scan date: **2026-07-23**  
Source: GitHub public repository metadata queried with `gh search repos`  
Authenticated account used only for API access: `KanadeK`

## Naming check

Exact searches for `WattWraith in:name` and `wattwraith in:name` returned no public
repositories. `KanadeK/wattwraith` did not exist at scan time. The project therefore
keeps the name **WattWraith** and slug **wattwraith**.

## Adjacent projects sampled

Stars and update timestamps are point-in-time metadata and will change.

| Repository | Stars | Updated (UTC) | Primary purpose | Estimated overlap |
| --- | ---: | --- | --- | ---: |
| [nilmtk/nilmtk](https://github.com/nilmtk/nilmtk) | 940 | 2026-07-20 | NILM toolkit for aggregate-load disaggregation | 35% |
| [JackKelly/neuralnilm](https://github.com/JackKelly/neuralnilm) | 160 | 2026-05-30 | Neural-network energy disaggregation research | 30% |
| [goruck/nilm](https://github.com/goruck/nilm) | 98 | 2026-07-03 | Real-time non-intrusive load monitoring | 40% |
| [pascme05/BaseNILM](https://github.com/pascme05/BaseNILM) | 30 | 2026-07-10 | Baseline NILM research tools | 35% |
| [robertvorthman/smart-plug-power-monitor](https://github.com/robertvorthman/smart-plug-power-monitor) | 27 | 2026-06-07 | Appliance state tracking from smart-switch power | 40% |
| [nneves/tplink-smartplug-tig](https://github.com/nneves/tplink-smartplug-tig) | 4 | 2021-04-22 | TP-Link collection and Grafana visualization | 30% |
| [Knapsacks/power-pi](https://github.com/Knapsacks/power-pi) | 2 | 2025-09-13 | Hardware/control approach to phantom-load reduction | 40% |
| [akugiz/smart-plug-energy-card](https://github.com/akugiz/smart-plug-energy-card) | 0 | 2026-07-23 | Home Assistant smart-plug energy and tariff card | 35% |
| [florencevaldezr/ecosync](https://github.com/florencevaldezr/ecosync) | 0 | 2026-04-19 | Web monitoring and vampire-power reduction | 60% |
| [JJC1138/smartplug-energy-logger](https://github.com/JJC1138/smartplug-energy-logger) | 0 | 2018-02-09 | TP-Link smart-plug energy logger | 20% |
| [nashrahjaan53-code/PowerGuard-AI](https://github.com/nashrahjaan53-code/PowerGuard-AI) | 0 | 2026-07-20 | Smart-meter anomaly detection | 25% |
| [vesanieminen/ElectricityCostDashboard](https://github.com/vesanieminen/ElectricityCostDashboard) | 56 | 2026-06-11 | Electricity cost dashboard | 25% |

## Decision and differentiation

No sampled active repository exceeded approximately 70% of the intended MVP scope.
The nearest project in this sample, EcoSync, has a related vampire-power goal, while
WattWraith narrows the implementation to an offline, device-level forensic audit:

- deterministic CSV/JSON smart-plug imports rather than live household telemetry;
- explainable baseline, periodic standby, overnight draw, and spike rules;
- confidence, measured evidence, and a verification plan for every conclusion;
- tariff repricing and week/month/year projections without re-running detection;
- explicit refusal to infer identity, occupancy, or sensitive behavior.

This is a dated, non-exhaustive public-repository sample. It supports the statement
that the scan found no active project with both the same name and a highly isomorphic
scope; it does not support a global uniqueness claim.

