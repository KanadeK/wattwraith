# WattWraith

WattWraith is an offline-first analyzer for smart-plug power time series. It is being
built to identify explainable standby and phantom-load patterns, then estimate energy
and cost savings without inferring who is at home or what a person is doing.

Current status: **v0.1.0 development**.

## Development setup

Python 3.12 is required.

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m mypy src
python -m pytest
```

The public-repository sample search found no active project with both the same name and
a highly isomorphic scope. See [the dated competitor scan](docs/COMPETITOR_SCAN.md) for
the sampled projects and the narrower claim this statement supports.

## Privacy boundary

The planned v0.1.0 workflow is local and offline. Device types will come only from user
annotations or clearly marked synthetic fixtures. Power readings will not be used to
infer identity, occupancy, sleep, work, or other sensitive personal behavior.

## License

[MIT](LICENSE)

