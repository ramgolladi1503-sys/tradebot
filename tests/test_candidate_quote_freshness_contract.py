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


def test_quote_freshness_contract_allows_fresh_executable_candidate():
    decision = classify_candidate_quote_freshness(_candidate())
    truth = classify_executable_truth(_candidate())

    assert decision.freshness_ok is True
    assert decision.reason_code == "ok"
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


def test_quote_freshness_contract_blocks_missing_option_token():
    decision = classify_candidate_quote_freshness(_candidate(instrument_token=None))
    truth = classify_executable_truth(_candidate(instrument_token=None))

    assert decision.freshness_ok is False
    assert "missing_option_token" in decision.reasons
    assert truth.execution_allowed is False
    assert "quote_freshness_contract_failed" in truth.reasons


def test_quote_freshness_contract_blocks_missing_tick_epoch():
    decision = classify_candidate_quote_freshness(_candidate(last_option_tick_epoch=None))

    assert decision.freshness_ok is False
    assert "missing_last_option_tick_epoch" in decision.reasons


def test_quote_freshness_contract_blocks_stale_ltp_bid_ask_quote_ages():
    decision = classify_candidate_quote_freshness(
        _candidate(
            ltp_age_sec=9.0,
            bid_age_sec=9.0,
            ask_age_sec=9.0,
            quote_age_sec=9.0,
        )
    )

    assert decision.freshness_ok is False
    assert "stale_candidate_quote:ltp_age_sec" in decision.reasons
    assert "stale_candidate_quote:bid_age_sec" in decision.reasons
    assert "stale_candidate_quote:ask_age_sec" in decision.reasons
    assert "stale_candidate_quote:quote_age_sec" in decision.reasons


def test_quote_freshness_contract_blocks_option_feed_blocker():
    decision = classify_candidate_quote_freshness(
        _candidate(option_feed_block_reason="STALE_OPTION_TICK")
    )

    assert decision.freshness_ok is False
    assert "stale_option_tick" in decision.reasons


def test_quote_freshness_contract_blocks_stale_chain_snapshot():
    decision = classify_candidate_quote_freshness(_candidate(chain_snapshot_age_sec=30.0))

    assert decision.freshness_ok is False
    assert "stale_chain_snapshot" in decision.reasons
