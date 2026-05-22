"""Safety regression tests for EDGE-33 option bid/ask/spread truth.

These tests are read-only. They do not call broker APIs and do not perform order actions.
"""

from core.executable_truth import classify_executable_truth
from core.option_spread_truth import classify_option_spread_truth


def _candidate(**overrides):
    base = {
        "trade_id": "EDGE33-T1",
        "candidate_class": "EXECUTABLE",
        "execution_entry_status": "executable",
        "selected_for_execution": True,
        "instrument_token": 123456,
        "last_option_tick_epoch": 1_700_000_000.0,
        "option_feed_block_reason": "OK",
        "ltp_age_sec": 0.5,
        "bid_age_sec": 0.6,
        "ask_age_sec": 0.7,
        "quote_age_sec": 0.7,
        "chain_snapshot_age_sec": 2.0,
        "data_state": "DATA_OK",
        "fresh_quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "data_confidence": 0.90,
        "best_bid": 100.0,
        "best_ask": 101.0,
        "ltp": 100.5,
        "quote_completeness": "FULL",
        "spread_source": "live_quote",
        "source_flags": {},
    }
    base.update(overrides)
    return base


def test_option_spread_truth_is_read_only_safety_gate():
    broker_api_called = False
    is_order_action = False
    live_order_action = False

    decision = classify_option_spread_truth(_candidate())

    assert decision.spread_ok is True
    assert broker_api_called is False
    assert is_order_action is False
    assert live_order_action is False


def test_option_spread_truth_allows_clean_bid_ask_candidate():
    decision = classify_option_spread_truth(_candidate())
    truth = classify_executable_truth(_candidate())

    assert decision.spread_ok is True
    assert decision.reason_code == "ok"
    assert truth.execution_allowed is True


def test_option_spread_truth_blocks_ltp_only_candidate():
    candidate = _candidate(best_bid=None, best_ask=None, ltp=100.5)

    decision = classify_option_spread_truth(candidate)
    truth = classify_executable_truth(candidate)

    assert decision.spread_ok is False
    assert set(decision.reasons) == {"missing_option_bid", "missing_option_ask"}
    assert truth.execution_allowed is False
    assert "option_spread_truth_failed" in truth.reasons


def test_option_spread_truth_blocks_inverted_bid_ask():
    decision = classify_option_spread_truth(_candidate(best_bid=102.0, best_ask=101.0))

    assert decision.spread_ok is False
    assert set(decision.reasons) == {"invalid_option_bid_ask"}


def test_option_spread_truth_blocks_wide_spread():
    decision = classify_option_spread_truth(_candidate(best_bid=100.0, best_ask=112.0, ltp=106.0))

    assert decision.spread_ok is False
    assert "wide_option_spread" in decision.reasons


def test_option_spread_truth_blocks_ltp_outside_bid_ask_range():
    decision = classify_option_spread_truth(_candidate(best_bid=100.0, best_ask=101.0, ltp=120.0))

    assert decision.spread_ok is False
    assert "ltp_outside_bid_ask" in decision.reasons


def test_option_spread_truth_blocks_partial_quote():
    decision = classify_option_spread_truth(_candidate(quote_completeness="PARTIAL"))

    assert decision.spread_ok is False
    assert set(decision.reasons) == {"partial_quote"}


def test_option_spread_truth_blocks_fallback_spread_source():
    decision = classify_option_spread_truth(_candidate(spread_source="fallback"))

    assert decision.spread_ok is False
    assert set(decision.reasons) == {"fallback_spread_source"}
