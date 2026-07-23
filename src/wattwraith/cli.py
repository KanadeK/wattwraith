"""Command-line interface for local WattWraith analysis."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from decimal import Decimal, InvalidOperation
from importlib.resources import as_file, files
from pathlib import Path

from pydantic import ValidationError

from wattwraith import __version__
from wattwraith.adapters import DataLoadError, load_annotations, load_tariff
from wattwraith.domain import FrameValidationError, TariffPlan
from wattwraith.services import analyze_file, write_report_bundle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wattwraith",
        description="Explainable, offline smart-plug standby analysis.",
    )
    parser.add_argument("--version", action="version", version=f"WattWraith {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze a local CSV or JSON smart-plug time series.",
    )
    analyze.add_argument("input", type=Path, help="CSV or JSON readings file")
    analyze.add_argument(
        "--annotations",
        type=Path,
        help="Optional JSON device annotation object keyed by device_id",
    )
    analyze.add_argument("--tariff", type=Path, help="Optional flat-tariff JSON file")
    analyze.add_argument(
        "--price-per-kwh",
        type=str,
        help="Override the tariff's energy price using an exact decimal",
    )
    analyze.add_argument(
        "--currency",
        type=str,
        help="Override the tariff currency with a three-letter ISO code",
    )
    analyze.add_argument(
        "--output-dir",
        type=Path,
        default=Path("wattwraith-output"),
        help="Destination for JSON, CSV, and HTML reports",
    )

    demo = subparsers.add_parser(
        "demo",
        help="Analyze the packaged deterministic four-device fixture.",
    )
    demo.add_argument(
        "--price-per-kwh",
        type=str,
        help="Override the packaged tariff's exact decimal energy price",
    )
    demo.add_argument("--currency", type=str, help="Override the packaged currency")
    demo.add_argument(
        "--output-dir",
        type=Path,
        default=Path("wattwraith-demo"),
        help="Destination for JSON, CSV, and HTML reports",
    )
    return parser


def _tariff_with_overrides(
    tariff: TariffPlan,
    *,
    price_per_kwh: str | None,
    currency: str | None,
) -> TariffPlan:
    try:
        price = Decimal(price_per_kwh) if price_per_kwh is not None else tariff.price_per_kwh
    except InvalidOperation as exc:
        raise ValueError("price-per-kwh must be a finite decimal") from exc
    return TariffPlan(
        currency=(currency or tariff.currency).upper(),
        price_per_kwh=price,
    )


def _packaged_path(name: str, stack: ExitStack) -> Path:
    resource = files("wattwraith.resources").joinpath(name)
    return stack.enter_context(as_file(resource))


def _run_analysis(
    input_path: Path,
    annotations_path: Path | None,
    tariff_path: Path | None,
    *,
    price_per_kwh: str | None,
    currency: str | None,
    output_dir: Path,
) -> dict[str, object]:
    annotations = load_annotations(annotations_path) if annotations_path else {}
    if tariff_path is None:
        with as_file(files("wattwraith.resources").joinpath("tariff.json")) as default_tariff:
            tariff = load_tariff(default_tariff)
    else:
        tariff = load_tariff(tariff_path)
    tariff = _tariff_with_overrides(
        tariff,
        price_per_kwh=price_per_kwh,
        currency=currency,
    )
    reports = analyze_file(input_path, annotations, tariff)
    paths = write_report_bundle(reports, output_dir)
    return {
        "status": "ok",
        "devices": len(reports),
        "price_per_kwh": str(tariff.price_per_kwh),
        "currency": tariff.currency,
        "outputs": {kind: str(path) for kind, path in paths.items()},
    }


def _run_demo(args: argparse.Namespace) -> dict[str, object]:
    with ExitStack() as stack:
        return _run_analysis(
            _packaged_path("smart_plug_week.csv", stack),
            _packaged_path("annotations.json", stack),
            _packaged_path("tariff.json", stack),
            price_per_kwh=args.price_per_kwh,
            currency=args.currency,
            output_dir=args.output_dir,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI, returning a conventional process status."""

    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            summary = _run_demo(args)
        else:
            summary = _run_analysis(
                args.input,
                args.annotations,
                args.tariff,
                price_per_kwh=args.price_per_kwh,
                currency=args.currency,
                output_dir=args.output_dir,
            )
    except (
        DataLoadError,
        FrameValidationError,
        ValidationError,
        ValueError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
