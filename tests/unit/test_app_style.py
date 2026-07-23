from wattwraith.app import _CSS


def test_metric_cards_keep_readable_text_on_light_background() -> None:
    assert '[data-testid="stMetric"] * { color:var(--ww-ink) !important; }' in _CSS
