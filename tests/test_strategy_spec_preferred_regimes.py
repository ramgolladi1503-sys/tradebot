from core.strategy_spec import build_strategy_spec_registry


def test_default_strategy_specs_expose_preferred_regimes():
    registry = build_strategy_spec_registry()

    nifty = registry.get("nifty_intraday")
    banknifty = registry.get("banknifty_intraday")
    sensex = registry.get("sensex_intraday")
    zero_hero = registry.get("zero_hero_expiry")

    assert nifty is not None
    assert nifty.preferred_regimes == ("BULL_TREND", "BEAR_TREND", "RANGE_BOUND")
    assert banknifty is not None
    assert banknifty.preferred_regimes == ("BULL_TREND", "BEAR_TREND", "RANGE_BOUND")
    assert sensex is not None
    assert sensex.preferred_regimes == ("BULL_TREND", "BEAR_TREND", "RANGE_BOUND")
    assert zero_hero is not None
    assert zero_hero.preferred_regimes == ("HIGH_VOLATILITY",)


def test_strategy_spec_payload_includes_preferred_regimes():
    registry = build_strategy_spec_registry()
    payload = registry.get("nifty_intraday").to_payload()

    assert payload["preferred_regimes"] == ["BULL_TREND", "BEAR_TREND", "RANGE_BOUND"]
