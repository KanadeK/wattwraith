# Benchmark

Measured on 2026-07-23 with the committed deterministic fixture.

| Field | Value |
| --- | --- |
| Machine | Windows-11-10.0.26200-SP0 |
| Python | 3.12.13 |
| Rows | 8064 |
| Devices | 4 |
| Repetitions | 5 |
| Median | 2.334 seconds |
| p95 | 2.660 seconds |

Command: `python scripts/benchmark.py`

This is an end-to-end local analysis benchmark, including deterministic clustering
and anomaly detection. It is not a smart-plug ingestion throughput claim.
