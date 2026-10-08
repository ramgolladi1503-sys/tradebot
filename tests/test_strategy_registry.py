from strategies.strategy_registry import load_strategy_registry


DECOMMISSIONED_STRATEGY_IDS = {
    "SIMPLE_ORB",
    "HTF_OPENING_DRIVE_CONT",
    "MEAN_REVERSION_EXTENSION",
    "COMPRESSION_BREAKOUT",
    "TREND_PULLBACK",
    "VWAP_RECLAIM",
    "OPENING_DRIVE",
    "FAILED_BREAKOUT_TRAP",
    "EXHAUSTION_REVERSAL",
    "EVENT_VOLATILITY_EXPANSION",
    "LATE_DAY_MOMENTUM",
    "OPTION_PRESSURE",
    "OPENING_RANGE_BREAKOUT",
    "NO_TRADE_CHOP",
    "PRO_STRATEGY_ENGINE",
    "ENSEMBLE",
    "TRADE_BUILDER",
    "NIFTY_INTRADAY",
    "BANKNIFTY_INTRADAY",
    "SENSEX_INTRADAY",
    "VWAP_ORB",
    "ZERO_HERO",
    "PAIRS_ARBITRAGE",
    "VOLATILITY_TREND",
}


def test_decommissioned_legacy_strategies_are_absent_from_registry():
    registry = load_strategy_registry()
    assert DECOMMISSIONED_STRATEGY_IDS.isdisjoint(registry)


def test_meg_remains_shadow_advisory_only():
    registry = load_strategy_registry()
    entry = registry["MARKET_EVENT_GRAPH_REVERSAL"]
    assert entry.strategy_kind == "candidate_generator_strategy"
    assert entry.certification_track == "shadow_live_observation_only"
    assert entry.certification_supported is False


def test_registry_contains_test_strat_excluded():
    registry = load_strategy_registry()
    entry = registry["TEST_STRAT"]
    assert entry.strategy_kind == "test_fixture"
    assert entry.certification_track == "not_certifiable"
    assert entry.certification_supported is False


def test_registry_retains_only_non_strategy_helpers():
    registry = load_strategy_registry()
    for strategy_id in {
        "RISK_MANAGER",
        "POSITION_SIZER",
        "SOFT_SIGNAL",
        "PRO_DECISION_ADAPTER",
    }:
        entry = registry[strategy_id]
        assert entry.strategy_kind == "helper_module"
        assert entry.certification_track == "not_certifiable"
        assert entry.certification_supported is False
