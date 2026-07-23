# Privacy and security model

WattWraith is designed for local review of device-level smart-plug time series. A power
trace can still reveal routines, so local processing does not make the input harmless.

## Data flow

1. The user selects a local CSV/JSON file or the explicit synthetic fixture.
2. The adapter validates size, schema, timestamp zone, labels, and power values.
3. The domain processes readings in memory.
4. Exports contain aggregates, evidence, and user annotations, not raw rows or source
   paths.
5. WattWraith makes no network request and emits no telemetry.

## Explicit privacy boundary

WattWraith does not infer:

- a person's identity;
- whether anyone is at home;
- sleeping, working, travel, or other personal schedules;
- household composition;
- appliance type from its waveform.

`device_type` and `display_name` originate only from a user annotation or a repository
fixture marked `annotation_origin="fixture"`. The phrase “overnight window” denotes a
configurable clock interval; it is not treated as a sleep window.

## Input protections

- 50 MiB default file limit and five-million-row domain limit
- accepted extensions limited to CSV and JSON
- exact required columns and no unit guessing
- finite, non-negative watts bounded at 100,000 W per reading
- timezone-aware timestamps
- long gaps excluded from energy integration
- safe errors containing only the input filename, never parent directories or rows

## Export protections

- JSON omits raw readings and absolute input paths.
- CSV prefixes cells beginning with `=`, `+`, `-`, or `@` to prevent formula execution.
- HTML escapes device labels and summaries.
- The static Pages report is generated exclusively from synthetic data.
- Users should encrypt or access-control reports derived from real household readings.

## Device safety

WattWraith is an analysis aid, not a power controller or electrical-safety system.

- `essential=true` cannot coexist with `shutdown_allowed=true`.
- Refrigerator recommendations remain monitoring and maintenance suggestions.
- Anomaly spikes are not counted as savings.
- Recommendations ask for one reversible, manufacturer-supported change and seven-day
  before/after measurement.
- The software does not send commands to a plug.

## Threats outside v0.1.0

- Malware or another local user reading source files or exports
- Spreadsheet applications that ignore CSV escaping conventions
- Deliberately adversarial files within the configured size limit
- Compromised Python packages or build infrastructure
- Inaccurate or unsafe user annotations

CI runs locked dependencies, static checks, tests, `pip-audit`, and a high-confidence
secret scan. Dependabot monitors the Python and GitHub Actions ecosystems.

## Reporting

Use GitHub private vulnerability reporting as described in [SECURITY.md](../SECURITY.md).
Do not attach a real power trace, credentials, or household metadata to a public issue.
