from core.strategy_spec import build_strategy_spec_registry
from strategies.banknifty_intraday import generate_signal as banknifty_generate_signal
from strategies.sensex_intraday import generate_signal as sensex_generate_signal
from strategies.zero_hero import zero_hero_strategy


def test_banknifty_and_sensex_share_the_same_preferred_regime_shape():
    registry = build_strategy_spec_registry()

    banknifty = registry.get("banknifty_intraday")
    sensex = registry.get("sensex_intraday")

    assert banknifty is not None
    assert sensex is not None
    assert banknifty.preferred_regimes == ("BULL_TREND", "BEAR_TREND", "RANGE_BOUND")
    assert sensex.preferred_regimes == ("BULL_TREND", "BEAR_TREND", "RANGE_BOUND")


def test_banknifty_range_path_is_mean_reversion():
    signal = banknifty_generate_signal(
        ltp=49000.0,
        vwap=50000.0,
        bias="bearish",
        regime="RANGE",
    )

    assert signal is not None
    assert signal["setup_type"] == "MEAN_REVERSION"
    assert signal["regime_path"] == "RANGE"


def test_sensex_unknown_regime_fails_closed():
    debug = {}
    signal = sensex_generate_signal(
        ltp=80000.0,
        vwap=79900.0,
        bias="bullish",
        regime="mystery",
        debug_stats=debug,
    )

    assert signal is None
    assert debug["candidates_rejected_pre_score"] == 1
    assert debug["rejection_reason_counts"]["regime_not_declared_by_strategy_spec"] == 1


def test_zero_hero_non_expiry_context_falls_back_to_directed_regime():
    trades = zero_hero_strategy(
        symbol="NIFTY",
        ltp=25000.0,
        premarket_bias={"bias": "bullish"},
        current_date=None,
        expiry_window_days=0,
        regime="mystery",
    )

    assert trades
    assert trades[0]["regime_path"] in {"TRENDING_UP", "TRENDING_DOWN"}
