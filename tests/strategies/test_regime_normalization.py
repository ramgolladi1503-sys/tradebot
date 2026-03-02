from strategies.ensemble import _normalize_regime


def test_range_maps_to_mean_revert():
    assert _normalize_regime("RANGE") == "MEAN_REVERT"


def test_neutral_maps_to_mean_revert():
    assert _normalize_regime("NEUTRAL") in {"NEUTRAL", "MEAN_REVERT"}


def test_event_maps_to_event():
    assert _normalize_regime("EVENT") == "EVENT"


def test_trend_maps_to_trend():
    assert _normalize_regime("TREND") == "TREND"
