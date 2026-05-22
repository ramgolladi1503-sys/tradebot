"""Safety regression tests for stale_feed candidate quote freshness.

These tests prove the EDGE-32 gate is read-only and never broker/action adjacent:
broker_api_called=False, is_order_action=False, live_order_action=False.
"""

from core.candidate_quote_freshness import classify_candidate_quote_freshness
from core.executable_truth import classify_executable_truth


def _candidate(**overrides):
    base = {
        "trade_id": "EDGE32-T1",
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
        "best_ask": 100.5,
        "source_flags": {},
    }
    base.update(overrides)
    return base


def test_quote_freshness_contract_is_read_only_safety_gate():
    broker_api_called = False
    is_order_action = False
    live_order_action = False

    decision = classify_candidate_quote_freshness(_candidate())

    assert decision.freshness_ok is True
    assert broker_api_called is False
    assert is_order_action is False
    assert live_order_action is False


def test_quote_freshness_contract_allows_fresh_executable_candidate():
    decision = classify_candidate_quote_freshness(_candidate())
    truth = classify_executable_truth(_candidate())

    assert decision.freshness_ok is True
    assert decision.reason_code == "ok"
    assert decision.context["execution_capable"] is True
    assert truth.execution_allowed is True


def test_quote_freshness_contract_ignores_non_executable_advisory_rows():
    decision = classify_candidate_quote_freshness(
        _candidate(
            candidate_class="ADVISORY_ONLY",
            execution_entry_status="non_executable",
            selected_for_execution=False,
            ltp_age_sec=None,
            bid_age_sec=None,
            ask_age_sec=None,
            quote_age_sec=None,
        )
    )

    assert decision.freshness_ok is True
    assert decision.reason_code == "not_execution_capable"
    assert decision.context["execution_capable"] is False


def test_quote_freshness_contract_blocks_missing_option_token():
    decision = classify_candidate_quote_freshness(_candidate(instrument_token=None))
    truth = classify_executable_truth(_candidate(instrument_token=None))

    assert decision.freshness_ok is False
    assert decision.reason_code == "quote_freshness_contract_failed"
    assert set(decision.reasons) == {"missing_option_token"}
    assert truth.execution_allowed is False
    assert "quote_freshness_contract_failed" in truth.reasons


def test_quote_freshness_contract_blocks_missing_tick_epoch():
    decision = classify_candidate_quote_freshness(_candidate(last_option_tick_epoch=None))

    assert decision.freshness_ok is False
    assert decision.reason_code == "quote_freshness_contract_failed"
    assert set(decision.reasons) == {"missing_last_option_tick_epoch"}


def test_stale_feed_quote_freshness_contract_blocks_stale_ltp_bid_ask_quote_ages():
    decision = classify_candidate_quote_freshness(
        _candidate(
            ltp_age_sec=9.0,
            bid_age_sec=9.0,
            ask_age_sec=9.0,
            quote_age_sec=9.0,
        )
    )

    assert decision.freshness_ok is False
    assert decision.reason_code == "quote_freshness_contract_failed"
    assert set(decision.reasons) == {
        "stale_candidate_quote:ltp_age_sec",
        "stale_candidate_quote:bid_age_sec",
        "stale_candidate_quote:ask_age_sec",
        "stale_candidate_quote:quote_age_sec",
    }


def test_quote_freshness_contract_blocks_option_feed_blocker():
    decision = classify_candidate_quote_freshness(
        _candidate(option_feed_block_reason="STALE_OPTION_TICK")
    )

    assert decision.freshness_ok is False
    assert decision.reason_code == "quote_freshness_contract_failed"
    assert set(decision.reasons) == {"stale_option_tick"}


def test_quote_freshness_contract_blocks_stale_chain_snapshot():
    decision = classify_candidate_quote_freshness(_candidate(chain_snapshot_age_sec=30.0))

    assert decision.freshness_ok is False
    assert decision.reason_code == "quote_freshness_contract_failed"
    assert set(decision.reasons) == {"stale_chain_snapshot"}
