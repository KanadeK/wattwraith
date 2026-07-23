"""Generate the reviewable static demo from committed synthetic readings."""

from __future__ import annotations

from datetime import UTC, datetime

from _common import ROOT, ensure_within_root

from wattwraith.adapters import load_annotations, load_power_file, load_tariff
from wattwraith.services import analyze_frame, reports_to_html, reports_to_json


class DemoClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 13, tzinfo=UTC)


def main() -> int:
    data_dir = ROOT / "examples" / "data"
    reports = analyze_frame(
        load_power_file(data_dir / "smart_plug_week.csv"),
        load_annotations(ROOT / "examples" / "annotations.json"),
        load_tariff(ROOT / "examples" / "tariff.json"),
        clock=DemoClock(),
    )
    site_dir = ensure_within_root(ROOT / "site")
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text(reports_to_html(reports), encoding="utf-8")
    (site_dir / "report.json").write_text(reports_to_json(reports), encoding="utf-8")
    print(f"Generated {site_dir / 'index.html'} from {len(reports)} device reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
