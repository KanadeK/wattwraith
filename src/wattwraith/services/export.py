"""Deterministic, injection-safe report exports."""

from __future__ import annotations

import csv
import html
import io
import json
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path

from wattwraith.domain import AnalysisReport


def _safe_spreadsheet_cell(value: str) -> str:
    return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value


def _annual_values(report: AnalysisReport) -> tuple[Decimal, Decimal, str]:
    annual = next(
        (estimate for estimate in report.savings.estimates if estimate.period == "year"),
        None,
    )
    if annual is None:
        return Decimal("0"), Decimal("0"), report.tariff.currency
    return annual.energy_kwh, annual.cost, annual.currency


def reports_to_json(reports: Iterable[AnalysisReport]) -> str:
    """Serialize public aggregates only; raw readings and source paths are excluded."""
    payload = {
        "schema_version": "1.0",
        "reports": [report.public_dump() for report in reports],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def reports_to_csv(reports: Iterable[AnalysisReport]) -> str:
    """Return a finding-level CSV suitable for independent review."""
    output = io.StringIO(newline="")
    fieldnames = (
        "device_id",
        "display_name",
        "finding",
        "status",
        "confidence",
        "confidence_grade",
        "rule_ids",
        "annual_energy_kwh",
        "annual_cost",
        "currency",
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for report in reports:
        annual_energy, annual_cost, currency = _annual_values(report)
        for result in report.results:
            writer.writerow(
                {
                    "device_id": _safe_spreadsheet_cell(report.annotation.device_id),
                    "display_name": _safe_spreadsheet_cell(
                        report.annotation.display_name or report.annotation.device_id
                    ),
                    "finding": result.kind.value,
                    "status": result.status.value,
                    "confidence": f"{result.confidence.score:.3f}",
                    "confidence_grade": result.confidence.grade.value,
                    "rule_ids": "|".join(item.rule_id for item in result.evidence),
                    "annual_energy_kwh": annual_energy,
                    "annual_cost": annual_cost,
                    "currency": currency,
                }
            )
    return output.getvalue()


def reports_to_html(reports: Iterable[AnalysisReport]) -> str:
    """Create a self-contained static summary from real report values."""
    report_list = list(reports)
    cards: list[str] = []
    total_energy = sum(float(_annual_values(report)[0]) for report in report_list)
    total_cost = sum(float(_annual_values(report)[1]) for report in report_list)
    currency = report_list[0].tariff.currency if report_list else ""
    for report in report_list:
        rows = "".join(
            "<tr>"
            f"<td>{html.escape(result.kind.value.replace('_', ' ').title())}</td>"
            f"<td>{html.escape(result.status.value)}</td>"
            f"<td>{result.confidence.score:.0%}</td>"
            f"<td>{html.escape(result.summary)}</td>"
            "</tr>"
            for result in report.results
        )
        annual_energy, annual_cost, annual_currency = _annual_values(report)
        label = html.escape(report.annotation.display_name or report.annotation.device_id)
        cards.append(
            f"<section><h2>{label}</h2>"
            f"<p><strong>{annual_energy} kWh/year</strong> · "
            f"{annual_cost} {html.escape(annual_currency)}/year</p>"
            "<table><thead><tr><th>Finding</th><th>Status</th>"
            "<th>Confidence</th><th>Rule summary</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></section>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WattWraith report</title>
<style>
:root{{--ink:#14231f;--muted:#63736e;--paper:#f4f1e8;--card:#fffdf7;--accent:#c64d2c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);
font:16px/1.55 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:3rem 1rem}}
h1{{font-size:clamp(2.4rem,7vw,5rem);letter-spacing:-.06em;margin:.2em 0}}
.lede{{max-width:65ch;color:var(--muted)}}.metric{{font-size:1.3rem;border-left:5px solid
var(--accent);padding:.6rem 1rem;background:var(--card)}}section{{background:var(--card);
padding:1.3rem;margin:1rem 0;border:1px solid #d8d3c8}}table{{width:100%;
border-collapse:collapse}}th,td{{text-align:left;padding:.65rem;border-bottom:1px solid #ddd}}
th{{font-size:.8rem;text-transform:uppercase}}@media(max-width:700px){{table{{font-size:.85rem}}
th,td{{padding:.35rem}}}}
</style></head><body><main><p>WATTWRAITH · SYNTHETIC DATA ONLY</p>
<h1>Standby power, made visible.</h1>
<p class="lede">This static report was generated locally from the repository's deterministic
smart-plug fixture. Confidence is rule strength, not a probability. No identity,
occupancy, sleep, or work behavior is inferred.</p>
<p class="metric">Projected avoidable energy: <strong>{total_energy:.3f} kWh/year</strong>
· estimated cost: <strong>{total_cost:.2f} {html.escape(currency)}/year</strong></p>
{"".join(cards)}
<footer><p>Verify savings with seven days before and after one reversible change.</p>
</footer></main></body></html>
"""


def write_report_bundle(
    reports: Iterable[AnalysisReport],
    output_dir: str | Path,
    *,
    stem: str = "wattwraith-report",
) -> dict[str, Path]:
    """Write JSON, CSV, and HTML from the same immutable reports."""
    report_list = tuple(reports)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": destination / f"{stem}.json",
        "csv": destination / f"{stem}.csv",
        "html": destination / f"{stem}.html",
    }
    paths["json"].write_text(reports_to_json(report_list), encoding="utf-8")
    paths["csv"].write_text(reports_to_csv(report_list), encoding="utf-8", newline="")
    paths["html"].write_text(reports_to_html(report_list), encoding="utf-8")
    return paths
