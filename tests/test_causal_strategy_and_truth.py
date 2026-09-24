from core.causal_pulse import create_native_pulse
from core.causal_strategy_harness import QualificationState, evaluate_causal_strategies
from core.causal_shadow_decision import evaluate_shadow_decision
from core.causal_trade_truth_emitter import build_canonical_trade_truth


def _pulse(session="cas-generic-signal-negative", sequence=1):
    return create_native_pulse(
        session_id=session,
        sequence_num=sequence,
        payload={"ltp": 25000.0},
        producer_sha="1" * 40,
    )


def test_generic_signal_does_not_enter_candidate_selection_or_trade_truth():
    pulse = _pulse()
    feed_health = {
        "websocket_ok": True,
        "feed_truth_state": "LIVE",
        "symbols": [{
            "symbol": "NIFTY",
            "feed_ok": True,
            "instrument_token": 256265,
            "option_last_tick_age_sec": 0.2,
            "confidence": 0.99,
            "direction": "BUY",
            "ltp": 25000.0,
            "is_completed_bar_signal": True,
        }],
    }
    strategy_result = evaluate_causal_strategies(
        pulse=pulse,
        market_snapshot={"market_open": True, "primary_regime": "TRENDING_BULLISH"},
        feed_health_truth=feed_health,
    )

    assert strategy_result.candidates == []
    assert strategy_result.observations[0].qualification_state is QualificationState.UNKNOWN
    decision = evaluate_shadow_decision(
        pulse=pulse,
        strategy_result=strategy_result,
        feed_health_truth=feed_health,
    )
    assert decision.selected_candidates == []
    assert decision.orders_placed == 0
    truth = build_canonical_trade_truth(
        pulse=pulse,
        market_snapshot={"market_open": True, "nifty_ltp": 25000.0},
        feed_health_truth=feed_health,
        strategy_result=strategy_result,
        decision_result=decision,
    )
    assert truth.decision.candidate_generated is False
    assert truth.execution.executable_market_state == "NOT_EXECUTABLE"
    assert truth.execution.broker_submission_authorized is False
    assert truth.execution.actual_broker_submission is False


def test_unregistered_symbols_are_inapplicable_even_with_high_confidence():
    pulse = _pulse("registry-authority")
    feed_health = {
        "websocket_ok": True,
        "symbols": [
            {"symbol": "NIFTY", "feed_ok": True, "instrument_token": 256265, "option_last_tick_age_sec": 0.1, "confidence": 0.95, "direction": "BUY"},
            {"symbol": "TCS26SEP3800CE", "feed_ok": False, "instrument_token": 999999, "option_last_tick_age_sec": 120.0, "confidence": 0.99, "direction": "BUY"},
        ],
    }
    result = evaluate_causal_strategies(
        pulse=pulse,
        market_snapshot={"primary_regime": "TRENDING_BULLISH"},
        feed_health_truth=feed_health,
    )

    assert result.candidates == []
    tcs = next(row for row in result.observations if row.symbol == "TCS26SEP3800CE")
    assert tcs.applicability_state.value == "INAPPLICABLE"
    assert tcs.reason_code == "REGISTRY_SYMBOL_NOT_APPLICABLE"


def test_empty_feed_produces_no_candidate_or_order_authority():
    pulse = _pulse("missing-inputs")
    strategy_result = evaluate_causal_strategies(
        pulse=pulse,
        market_snapshot=None,
        feed_health_truth={"websocket_ok": True, "symbols": []},
    )
    decision = evaluate_shadow_decision(
        pulse=pulse,
        strategy_result=strategy_result,
        feed_health_truth={"websocket_ok": True, "symbols": []},
    )

    assert strategy_result.evaluated_symbol_count == 0
    assert strategy_result.candidates == []
    assert decision.selected_candidates == []
    assert decision.order_authority is False
    assert decision.broker_write_authority is False
    assert decision.orders_placed == decision.orders_modified == decision.orders_cancelled == 0
