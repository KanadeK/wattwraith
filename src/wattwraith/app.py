"""Streamlit interface backed exclusively by WattWraith's domain services."""

from __future__ import annotations

from contextlib import ExitStack
from decimal import Decimal
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import TemporaryDirectory

import plotly.express as px  # type: ignore[import-untyped]
import polars as pl
import streamlit as st
from pydantic import ValidationError

from wattwraith.adapters import DataLoadError, load_annotations, load_power_file, load_tariff
from wattwraith.domain import AnalysisReport, DeviceAnnotation, TariffPlan
from wattwraith.services import (
    analyze_frame,
    reports_to_csv,
    reports_to_html,
    reports_to_json,
)

_CSS = """
<style>
:root { --ww-ink:#17231f; --ww-muted:#60706a; --ww-paper:#f3efe4; --ww-accent:#b8472c; }
.stApp { background:var(--ww-paper); color:var(--ww-ink); }
.block-container { max-width:1180px; padding-top:2rem; }
h1 { letter-spacing:-.045em; line-height:.95; }
[data-testid="stMetric"] { background:#fffdf7; border:1px solid #d8d1c2; padding:1rem; }
button:focus-visible, input:focus-visible, [role="button"]:focus-visible {
  outline:3px solid var(--ww-accent) !important; outline-offset:3px;
}
.ww-note { border-left:4px solid var(--ww-accent); padding:.7rem 1rem; background:#fffdf7; }
@media (max-width:700px) {
  .block-container { padding:1rem .75rem; }
  h1 { font-size:2.35rem !important; }
}
</style>
"""


def _packaged_demo() -> tuple[pl.DataFrame, dict[str, DeviceAnnotation], TariffPlan]:
    with ExitStack() as stack:
        data_path = stack.enter_context(
            as_file(files("wattwraith.resources").joinpath("smart_plug_week.csv"))
        )
        annotation_path = stack.enter_context(
            as_file(files("wattwraith.resources").joinpath("annotations.json"))
        )
        tariff_path = stack.enter_context(
            as_file(files("wattwraith.resources").joinpath("tariff.json"))
        )
        return (
            load_power_file(data_path),
            load_annotations(annotation_path),
            load_tariff(tariff_path),
        )


def _uploaded_frame(uploaded: object) -> pl.DataFrame:
    name = Path(str(getattr(uploaded, "name", "upload.csv"))).name
    suffix = Path(name).suffix.lower()
    if suffix not in {".csv", ".json"}:
        raise DataLoadError("Upload must use a .csv or .json extension")
    data = uploaded.getvalue()  # type: ignore[attr-defined]
    if len(data) > 50 * 1024 * 1024:
        raise DataLoadError("Upload exceeds the 50 MiB safety limit")
    with TemporaryDirectory(prefix="wattwraith-upload-") as directory:
        path = Path(directory) / f"upload{suffix}"
        path.write_bytes(data)
        return load_power_file(path)


def _annotation_controls(
    frame: pl.DataFrame,
    defaults: dict[str, DeviceAnnotation],
) -> dict[str, DeviceAnnotation]:
    annotations: dict[str, DeviceAnnotation] = {}
    st.subheader("Device annotations")
    st.caption("Types and labels are explicit annotations; WattWraith never guesses them.")
    for device_id in sorted(frame.get_column("device_id").unique().to_list()):
        default = defaults.get(device_id, DeviceAnnotation(device_id=device_id))
        with st.expander(default.display_name or device_id, expanded=len(defaults) == 0):
            label = st.text_input(
                "Display label",
                value=default.display_name or device_id,
                key=f"label-{device_id}",
            )
            device_type = st.selectbox(
                "Device type",
                ("unknown", "refrigerator", "television", "game_console", "printer"),
                index=("unknown", "refrigerator", "television", "game_console", "printer").index(
                    default.device_type
                ),
                key=f"type-{device_id}",
            )
            essential = st.checkbox(
                "Essential / must not be switched off",
                value=default.essential,
                key=f"essential-{device_id}",
            )
            target = st.number_input(
                "User-approved standby target (W)",
                min_value=0.0,
                max_value=25_000.0,
                value=float(default.standby_target_w or 1.0),
                step=0.1,
                key=f"target-{device_id}",
            )
            allow_shutdown = st.checkbox(
                "A scheduled shutdown is safe",
                value=default.shutdown_allowed and not essential,
                disabled=essential,
                key=f"shutdown-{device_id}",
            )
        annotations[device_id] = DeviceAnnotation(
            device_id=device_id,
            display_name=label,
            device_type=device_type,
            annotation_origin=default.annotation_origin,
            timezone=default.timezone,
            essential=essential,
            shutdown_allowed=allow_shutdown and not essential,
            standby_target_w=target,
        )
    return annotations


def _render_reports(frame: pl.DataFrame, reports: tuple[AnalysisReport, ...]) -> None:
    st.subheader("Power timeline")
    figure = px.line(
        frame,
        x="timestamp",
        y="watts",
        color="device_id",
        labels={"timestamp": "UTC time", "watts": "Power (W)", "device_id": "Device"},
    )
    figure.update_layout(
        template="plotly_white",
        legend_title_text="Device",
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
    )
    st.plotly_chart(figure, width="stretch")

    for report in reports:
        st.markdown(f"### {report.annotation.display_name or report.annotation.device_id}")
        columns = st.columns(3)
        annual = next((item for item in report.savings.estimates if item.period == "year"), None)
        columns[0].metric(
            "Annual potential",
            f"{annual.energy_kwh if annual else Decimal('0')} kWh",
        )
        columns[1].metric(
            "Annual estimated cost",
            f"{annual.cost if annual else Decimal('0')} "
            f"{annual.currency if annual else report.tariff.currency}",
        )
        columns[2].metric("Data coverage", f"{report.coverage:.1%}")

        estimate_rows = [
            {
                "period": estimate.period,
                "days": str(estimate.days),
                "energy_kwh": str(estimate.energy_kwh),
                "cost": str(estimate.cost),
                "currency": estimate.currency,
            }
            for estimate in report.savings.estimates
        ]
        if estimate_rows:
            st.dataframe(estimate_rows, width="stretch", hide_index=True)
        else:
            st.info(report.savings.suppression_reason or "No projectable waste detected.")

        for result in report.results:
            with st.expander(
                f"{result.kind.value.replace('_', ' ').title()} · "
                f"{result.status.value} · {result.confidence.score:.0%}"
            ):
                st.write(result.summary)
                st.caption("Confidence is reproducible rule strength, not probability.")
                st.dataframe(
                    [
                        {
                            "rule": item.rule_id,
                            "metric": item.metric,
                            "observed": str(item.observed),
                            "operator": str(item.operator),
                            "threshold": str(item.threshold),
                            "passed": item.passed,
                            "explanation": item.explanation,
                        }
                        for item in result.evidence
                    ],
                    width="stretch",
                    hide_index=True,
                )

    st.subheader("Download this analysis")
    json_text = reports_to_json(reports)
    csv_text = reports_to_csv(reports)
    html_text = reports_to_html(reports)
    downloads = st.columns(3)
    downloads[0].download_button(
        "Download JSON", json_text, "wattwraith-report.json", "application/json"
    )
    downloads[1].download_button("Download CSV", csv_text, "wattwraith-report.csv", "text/csv")
    downloads[2].download_button("Download HTML", html_text, "wattwraith-report.html", "text/html")


def main() -> None:
    st.set_page_config(
        page_title="WattWraith",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_CSS, unsafe_allow_html=True)
    st.title("Standby power, made visible.")
    st.markdown(
        '<p class="ww-note">Analyze smart-plug CSV or JSON locally. No telemetry, '
        "device guessing, identity, presence, sleep, or work-schedule inference.</p>",
        unsafe_allow_html=True,
    )

    try:
        source = st.radio(
            "Data source",
            ("Packaged demo", "Upload CSV or JSON"),
            horizontal=True,
        )
        defaults: dict[str, DeviceAnnotation]
        if source == "Packaged demo":
            frame, defaults, default_tariff = _packaged_demo()
            st.caption("Deterministic synthetic refrigerator, TV, console, and printer data.")
        else:
            uploaded = st.file_uploader(
                "Smart-plug readings",
                type=("csv", "json"),
                help="Required columns: timestamp, device_id, watts. Maximum 50 MiB.",
            )
            if uploaded is None:
                st.info("Choose a CSV or JSON file to configure and run analysis.")
                return
            frame = _uploaded_frame(uploaded)
            defaults = {}
            with as_file(files("wattwraith.resources").joinpath("tariff.json")) as tariff_path:
                default_tariff = load_tariff(tariff_path)

        with st.sidebar:
            st.header("Tariff")
            price = st.number_input(
                "Price per kWh",
                min_value=0.0,
                max_value=1_000_000.0,
                value=float(default_tariff.price_per_kwh),
                step=0.01,
            )
            currency = st.text_input(
                "Currency (ISO 4217)",
                value=default_tariff.currency,
                max_chars=3,
            ).upper()
            st.caption("Fixed charges, taxes, tiers, and seasonal changes are excluded.")

        annotations = _annotation_controls(frame, defaults)
        if st.button("Run real analysis", type="primary", width="stretch"):
            tariff = TariffPlan(
                currency=currency,
                price_per_kwh=Decimal(str(price)),
            )
            reports = analyze_frame(frame, annotations, tariff)
            _render_reports(frame, reports)
    except (DataLoadError, ValidationError, ValueError, OSError) as exc:
        st.error(f"Analysis could not run: {exc}")
        st.caption("No partial or fabricated result was produced.")


if __name__ == "__main__":
    main()
