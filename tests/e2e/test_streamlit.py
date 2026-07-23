from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.e2e
def test_streamlit_demo_runs_analysis_and_renders_real_results() -> None:
    app = AppTest.from_file(ROOT / "src" / "wattwraith" / "app.py", default_timeout=60)
    app.run()
    assert not app.exception
    assert any(button.label == "Run real analysis" for button in app.button)

    run_button = next(button for button in app.button if button.label == "Run real analysis")
    run_button.click().run(timeout=60)

    assert not app.exception
    assert len(app.metric) == 12
    assert any(metric.label == "Annual potential" for metric in app.metric)
    assert any("Baseline" in expander.label for expander in app.expander)
    assert len(app.dataframe) >= 8
