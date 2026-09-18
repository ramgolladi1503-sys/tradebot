"""Tests for Hops 5-12 (Canonical Strategy evaluation, Selection, Risk, and Trade Truth)."""
import pytest
from core.causal_pulse import create_native_pulse
from core.causal_strategy_harness import evaluate_causal_strategies
from core.causal_shadow_decision import evaluate_shadow_decision
from core.causal_trade_truth_emitter import build_canonical_trade_truth


def test_causal_12hop_shadow_lineage():
    producer_sha = "49f813899d062b33ad6d2f3b8231470ff8f31d94"
    session_id = "test-live-session-001"

    # Hop 1-4: Pulse creation from normalized tick
    pulse = create_native_pulse(
        session_id=session_id,
        sequence_num=101,
        payload={"nifty_ltp": 24500.0, "timestamp": 1789710000.0},
        producer_sha=producer_sha,
    )

    feed_health = {
        "websocket_ok": True,
        "feed_truth_state": "LIVE",
        "symbols": [
            {"symbol": "RELIANCE", "feed_ok": True, "instrument_token": 738561, "option_last_tick_age_sec": 0.2, "confidence": 0.85, "direction": "BUY", "ltp": 2950.0},
            {"symbol": "TCS", "feed_ok": False, "instrument_token": 895745, "option_last_tick_age_sec": 5.4},
        ]
    }

    # Hop 5-8: Strategy evaluation via canonical registry/signal engine
    strat_res = evaluate_causal_strategies(
        pulse=pulse,
        market_snapshot={"market_open": True, "nifty_ltp": 24500.0, "primary_regime": "TRENDING_BULLISH"},
        feed_health_truth=feed_health,
    )
    assert strat_res.pulse_id == pulse.pulse_id
    assert strat_res.evaluated_symbol_count == 2
    assert strat_res.regime == "TRENDING_BULLISH"
    assert len(strat_res.candidates) == 1
    assert strat_res.candidates[0].symbol == "RELIANCE"

    # TCS is rejected due to stale feed >2.5s
    tcs_rej = next(r for r in strat_res.rejections if r["symbol"] == "TCS")
    assert tcs_rej["reason_code"] == "REJECT_FEED_DEGRADED_OR_STALE"

    # Hop 9-10: Shadow Decision & Risk via canonical select_best_opportunity and RiskEngine
    decision_res = evaluate_shadow_decision(
        pulse=pulse,
        strategy_result=strat_res,
        feed_health_truth=feed_health,
    )
    assert decision_res.pulse_id == pulse.pulse_id
    assert decision_res.read_only is True
    assert decision_res.order_authority is False
    assert decision_res.orders_placed == 0
    assert len(decision_res.selected_candidates) == 1

    # Hop 11-12: Canonical Trade Truth Record
    truth = build_canonical_trade_truth(
        pulse=pulse,
        market_snapshot={"market_open": True, "nifty_ltp": 24500.0},
        feed_health_truth=feed_health,
        strategy_result=strat_res,
        decision_result=decision_res,
    )

    assert truth.identity.trace_id == pulse.pulse_id
    assert truth.identity.session_id == session_id
    assert truth.identity.instrument == "RELIANCE"
    assert truth.decision.candidate_generated is True
    assert truth.execution.actual_broker_submission is False
    assert truth.execution.broker_submission_authorized is False
    assert truth.orders_placed == 0
    assert truth.record_hash != ""


