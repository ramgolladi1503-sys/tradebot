from __future__ import annotations

from core.executable_truth import classify_executable_truth
from core.symbol_execution_safety import (
    SYMBOL_EXECUTION_SAFETY_BLOCK_REASON,
    SYMBOL_FEED_UNSAFE_REASON,
    SYMBOL_MISSING_REASON,
    SYMBOL_OPTION_BLOCKED_REASON,
    SYMBOL_STALE_OPTION_REASON,
    SYMBOL_SUBSCRIPTION_FAILED_REASON,
    classify_symbol_execution_safety,
    resolve_candidate_symbol,
)


def _candidate(**overrides):
    candidate = {
        "symbol": "NIFTY",
        "candidate_class": "EXECUTABLE",
        "execution_entry_status": "executable",
        "signal_valid": True,
        "signal_strength": 0.8,
        "fresh_quote_ok": True,
        "spread_ok": True,
        "liquidity_ok": True,
        "data_confidence": 0.95,
        "current_ltp": 100.0,
        "best_bid": 99.8,
        "best_ask": 100.2,
        "quote_source": "kite_ws",
        "option_ltp_source": "kite_ws",
        "quote_validation_status": "OK",
        "quote_age_sec": 0.5,
        "quote_ts_age_sec": 0.5,
        "quote_report_age_sec": 0.5,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.5},
        "symbol_feed_ok_by_symbol": {"NIFTY": True},
        "feed_ok": True,
        "ws_connected": True,
        "effective_ws_connected": True,
    }
    candidate.update(overrides)
    return candidate


def test_resolve_candidate_symbol_uses_direct_symbol_first():
    assert resolve_candidate_symbol(_candidate(symbol="banknifty", underlying="NIFTY")) == "BANKNIFTY"


def test_symbol_execution_safety_allows_clean_symbol_feed():
    decision = classify_symbol_execution_safety(_candidate())

    assert decision.execution_allowed is True
    assert decision.reason_code == "ok"
    assert decision.reasons == ()
    assert decision.symbol == "NIFTY"
    assert decision.context["feed_health_truth"]["feed_ok"] is True


def test_symbol_execution_safety_blocks_missing_symbol():
    candidate = _candidate(symbol=None, underlying=None, underlying_symbol=None, index_symbol=None)

    decision = classify_symbol_execution_safety(candidate)

    assert decision.execution_allowed is False
    assert decision.reason_code == SYMBOL_EXECUTION_SAFETY_BLOCK_REASON
    assert decision.reasons == (SYMBOL_MISSING_REASON,)


def test_symbol_execution_safety_blocks_stale_symbol_option_ticks():
    decision = classify_symbol_execution_safety(
        _candidate(option_last_tick_age_by_symbol={"NIFTY": 12.0})
    )

    assert decision.execution_allowed is False
    assert SYMBOL_STALE_OPTION_REASON in decision.reasons
    assert decision.context["feed_health_truth"]["symbols"][0]["feed_ok"] is False


def test_symbol_execution_safety_blocks_global_feed_unsafe_for_symbol():
    decision = classify_symbol_execution_safety(_candidate(feed_ok=False))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_UNSAFE_REASON in decision.reasons


def test_symbol_execution_safety_preserves_subscription_failure_reason():
    decision = classify_symbol_execution_safety(
        _candidate(option_feed_block_reason_by_symbol={"NIFTY": "subscription_failed"})
    )

    assert decision.execution_allowed is False
    assert SYMBOL_OPTION_BLOCKED_REASON in decision.reasons
    assert SYMBOL_SUBSCRIPTION_FAILED_REASON in decision.reasons


def test_executable_truth_blocks_when_symbol_feed_is_stale():
    decision = classify_executable_truth(
        _candidate(option_last_tick_age_by_symbol={"NIFTY": 10.0})
    )

    assert decision.execution_allowed is False
    assert SYMBOL_EXECUTION_SAFETY_BLOCK_REASON in decision.reasons
    assert SYMBOL_STALE_OPTION_REASON in decision.reasons
    assert decision.context["symbol_execution_safety"]["symbol"] == "NIFTY"


def test_executable_truth_allows_clean_symbol_safety_when_other_truths_are_clean():
    decision = classify_executable_truth(_candidate())

    assert decision.execution_allowed is True
    assert decision.reason_code == "ok"
    assert decision.context["symbol_execution_safety"]["execution_allowed"] is True
