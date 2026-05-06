from __future__ import annotations

from strategies.pro_layer.pro_decision_adapter import best_pro_strategy_decision, evaluate_pro_strategy_candidates


def test_pro_strategy_replay_is_deterministic():
    market_data = {
        "symbol": "NIFTY",
        "instrument_id": "789",
        "regime": "TREND",
        "atr": 1.8,
        "ltp_change_window": 1.45,
        "vol_z": 1.7,
        "bid_qty": 860,
        "ask_qty": 120,
        "quote_age_sec": 1.1,
        "spread_pct": 0.009,
        "quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "execution_allowed": True,
        "data_confidence": 0.92,
    }
    first = evaluate_pro_strategy_candidates(market_data)
    second = evaluate_pro_strategy_candidates(dict(market_data))
    assert first == second
    assert best_pro_strategy_decision(market_data) == (first[0] if first else None)


def test_pro_strategy_replay_fails_closed_on_stale_input():
    market_data = {
        "symbol": "NIFTY",
        "instrument_id": "789",
        "regime": "TREND",
        "atr": 1.8,
        "ltp_change_window": 1.45,
        "vol_z": 1.7,
        "bid_qty": 860,
        "ask_qty": 120,
        "quote_age_sec": 14.0,
        "spread_pct": 0.032,
        "quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "execution_allowed": True,
        "data_confidence": 0.38,
    }
    assert evaluate_pro_strategy_candidates(market_data) == []
    assert best_pro_strategy_decision(market_data) is None
