from __future__ import annotations

from core.decision_dag import REASON_FEED_STALE, REASON_INDICATORS_MISSING, evaluate_decision


_STRATEGY_CANDIDATES = [{"family": "BREAKOUT", "allowed": True, "reasons": []}]


def _base_market_data(**overrides):
    data = {
        "symbol": "NIFTY",
        "execution_mode": "LIVE",
        "market_open": True,
        "segment": "NSE_FNO",
        "instrument": "OPT",
        "timestamp": 1_000.0,
        "ltp": 100.0,
        "ltp_ts_epoch": 999.5,
        "latest_option_tick_ts": 999.5,
        "ws_connected": True,
        "subscribed_option_tokens_count": 12,
        "ohlc_bars_count": 60,
        "warmup_min_bars": 50,
        # Intentionally "true" to prove strict gating uses required-indicator presence too.
        "indicators_ok": True,
        "indicator_last_update_epoch": 999.0,
        "indicators_age_sec": 1.0,
        "compute_indicators_error": "",
        "vwap": 100.0,
        "rsi": 55.0,
        "ema": 101.0,
        "atr": 12.0,
        "primary_regime": "TREND",
        "regime": "TREND",
        "regime_prob_max": 0.99,
        "regime_entropy": 0.01,
        "risk_ok": True,
        "broker_enabled": True,
        "bid": 99.5,
        "ask": 100.5,
    }
    data.update(overrides)
    return data


def test_feed_live_but_indicators_missing_blocks_executable_and_exposes_missing_fields():
    decision = evaluate_decision(_base_market_data(vwap=None), strategy_candidates=_STRATEGY_CANDIDATES)

    assert decision.allowed is False
    assert decision.primary_blocker == REASON_INDICATORS_MISSING
    assert REASON_INDICATORS_MISSING in decision.blockers

    warmup = next(row for row in decision.explain if row.get("node") == "N3_WARMUP_DONE")
    facts = warmup["facts"]
    assert "indicator_missing_inputs" in facts
    assert "vwap" in facts["indicator_missing_inputs"]


def test_feed_dead_beats_indicator_missing_as_primary_blocker():
    decision = evaluate_decision(
        _base_market_data(
            vwap=None,
            # Force feed stale: both ltp and option tick are far older than max ages.
            ltp_ts_epoch=0.0,
            latest_option_tick_ts=0.0,
        ),
        strategy_candidates=_STRATEGY_CANDIDATES,
    )

    assert decision.allowed is False
    assert decision.primary_blocker == REASON_FEED_STALE
    assert REASON_FEED_STALE in decision.blockers
    # Indicator missing may still be present, but must not win as primary blocker.
    assert REASON_INDICATORS_MISSING in decision.blockers


def test_indicator_readiness_recovers_without_restart_allows_candidate_generation():
    blocked = evaluate_decision(_base_market_data(vwap=None), strategy_candidates=_STRATEGY_CANDIDATES)
    assert blocked.allowed is False
    assert blocked.primary_blocker == REASON_INDICATORS_MISSING

    recovered = evaluate_decision(_base_market_data(vwap=100.0), strategy_candidates=_STRATEGY_CANDIDATES)
    assert recovered.allowed is True
    assert recovered.primary_blocker is None
