from core.strategy_spec import (
    FAMILY_EVENT,
    FAMILY_MOVEMENT,
    FAMILY_PRO_STRATEGY,
    build_strategy_spec_registry,
)


def test_registry_includes_remaining_movement_and_event_families():
    registry = build_strategy_spec_registry()

    expected = {
        "opening_drive": FAMILY_MOVEMENT,
        "compression_breakout": FAMILY_MOVEMENT,
        "failed_breakout_trap": FAMILY_MOVEMENT,
        "exhaustion_reversal": FAMILY_MOVEMENT,
        "late_day_momentum": FAMILY_MOVEMENT,
        "vwap_reclaim_rejection": FAMILY_MOVEMENT,
        "option_pressure_confirmation": FAMILY_MOVEMENT,
        "event_volatility_expansion": FAMILY_EVENT,
        "no_trade_chop": FAMILY_EVENT,
        "pro_strategy": FAMILY_PRO_STRATEGY,
    }

    for strategy_id, family in expected.items():
        spec = registry.get(strategy_id)
        assert spec is not None
        assert spec.family == family


def test_remaining_family_specs_expose_expected_evidence_and_regimes():
    registry = build_strategy_spec_registry()

    pro = registry.get("pro_strategy")
    event = registry.get("event_volatility_expansion")
    no_trade = registry.get("no_trade_chop")

    assert pro is not None
    assert "signal_quality" in pro.required_evidence_keys
    assert "candidate_truth" in pro.required_evidence_keys
    assert "family_truth" in pro.required_evidence_keys

    assert event is not None
    assert "event_state" in event.required_evidence_keys
    assert "volatility_state" in event.required_evidence_keys
    assert event.preferred_regimes == ("HIGH_VOLATILITY", "MIXED_UNCERTAIN")

    assert no_trade is not None
    assert no_trade.direction_capabilities == ("NEUTRAL",)
    assert no_trade.preferred_regimes == ("RANGE_BOUND", "MIXED_UNCERTAIN")


def test_registry_includes_volatility_trend_family():
    registry = build_strategy_spec_registry()
    volatility_trend = registry.get("volatility_trend")

    assert volatility_trend is not None
    assert "atr_state" in volatility_trend.required_evidence_keys
    assert "cross_asset_health" in volatility_trend.required_evidence_keys
    assert volatility_trend.preferred_regimes == ("HIGH_VOLATILITY", "BULL_TREND", "BEAR_TREND")
