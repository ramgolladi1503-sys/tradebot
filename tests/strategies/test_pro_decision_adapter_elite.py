from __future__ import annotations

from strategies.pro_layer.pro_decision_adapter import pro_signal_to_candidate
from strategies.pro_layer.pro_strategy_engine import ProSignal


def test_adapter_penalizes_stale_and_weak_quality():
    signal = ProSignal(
        name="vol_expansion",
        direction="BUY_CALL",
        score=0.92,
        confidence=0.90,
        reason="high-momentum confirmation",
        family="volatility_expansion",
        regime_tags=["TREND"],
        evidence={"move_atr": 1.9},
    )
    market_data = {
        "symbol": "NIFTY",
        "instrument_id": "123",
        "quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "execution_allowed": True,
        "quote_age_sec": 14.0,
        "spread_pct": 0.032,
        "data_confidence": 0.38,
    }
    candidate = pro_signal_to_candidate(signal, market_data)
    assert candidate["tradable"] is False
    assert candidate["execution_allowed"] is False
    assert candidate["confidence_final"] < candidate["raw_edge_score"]
    assert candidate["rank_score"] < candidate["raw_edge_score"]


def test_adapter_refuses_external_tradable_override_when_quality_is_weak():
    signal = ProSignal(
        name="options_flow_alignment",
        direction="BUY_PUT",
        score=0.86,
        confidence=0.88,
        reason="aligned options flow",
        family="options_flow",
        regime_tags=["TREND"],
        evidence={"oi_pressure": 14.0},
    )
    candidate = pro_signal_to_candidate(
        signal,
        {
            "symbol": "NIFTY",
            "instrument_id": "123",
            "quote_ok": True,
            "liquidity_ok": True,
            "spread_ok": True,
            "execution_allowed": True,
            "tradable": True,
            "quote_age_sec": 8.0,
            "spread_pct": 0.029,
            "data_confidence": 0.41,
        },
    )
    assert candidate["tradable"] is False
    assert candidate["execution_allowed"] is False
    assert candidate["source_flags"]["pro_rank_quality"] < 0.65


def test_adapter_preserves_signal_provenance():
    signal = ProSignal(
        name="liquidity_imbalance",
        direction="BUY_PUT",
        score=0.80,
        confidence=0.84,
        reason="depth imbalance",
        family="order_flow",
        regime_tags=["TREND"],
        evidence={"imbalance": -0.41},
    )
    candidate = pro_signal_to_candidate(
        signal,
        {
            "symbol": "BANKNIFTY",
            "instrument_id": "456",
            "quote_ok": True,
            "liquidity_ok": True,
            "spread_ok": True,
            "execution_allowed": True,
            "data_confidence": 0.88,
            "quote_age_sec": 1.0,
            "spread_pct": 0.01,
        },
    )
    assert candidate["source_flags"]["strategy_name"] == "liquidity_imbalance"
    assert candidate["source_flags"]["pro_signal"]["family"] == "order_flow"
    assert candidate["source_flags"]["pro_signal"]["evidence"]["imbalance"] == -0.41


def test_adapter_parses_string_booleans_conservatively():
    signal = ProSignal(
        name="liquidity_imbalance",
        direction="BUY_CALL",
        score=0.84,
        confidence=0.82,
        reason="depth imbalance",
        family="order_flow",
        regime_tags=["TREND"],
        evidence={"imbalance": 0.31},
    )
    candidate = pro_signal_to_candidate(
        signal,
        {
            "symbol": "NIFTY",
            "instrument_id": "789",
            "quote_ok": "true",
            "liquidity_ok": "true",
            "spread_ok": "true",
            "execution_allowed": "true",
            "tradable": "false",
            "data_confidence": 0.9,
            "quote_age_sec": 1.0,
            "spread_pct": 0.01,
        },
    )
    assert candidate["tradable"] is False
