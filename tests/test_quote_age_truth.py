from __future__ import annotations

from core.candidate_quote_freshness import QUOTE_FRESHNESS_BLOCK_REASON, classify_candidate_quote_freshness
from core.quote_age_truth import QUOTE_AGE_TIMESTAMP_MISMATCH, classify_quote_age_truth


def _execution_candidate(**overrides):
    payload = {
        "candidate_class": "EXECUTABLE",
        "execution_entry_status": "executable",
        "instrument_token": 12345,
        "quote_ts_epoch": 1_700_000_000.0,
        "ts_epoch": 1_700_000_001.0,
        "quote_age_sec": 1.0,
        "ltp_age_sec": 1.0,
        "bid_age_sec": 1.0,
        "ask_age_sec": 1.0,
        "chain_snapshot_age_sec": 1.0,
        "option_feed_block_reason": "OK",
        "market_mode": "LIVE",
    }
    payload.update(overrides)
    return payload


def test_quote_age_truth_uses_timestamp_when_reported_age_is_missing():
    decision = classify_quote_age_truth(
        {
            "quote_ts_epoch": 1_700_000_000.0,
            "ts_epoch": 1_700_000_012.5,
        }
    )

    assert decision.ok is True
    assert decision.effective_age_sec == 12.5
    assert decision.timestamp_age_sec == 12.5
    assert decision.reported_age_sec is None


def test_quote_age_truth_blocks_reported_fresh_age_when_timestamp_is_stale():
    decision = classify_quote_age_truth(
        {
            "quote_ts_epoch": 1_700_000_000.0,
            "ts_epoch": 1_700_600_000.0,
            "quote_age_sec": 1.0,
        },
        mismatch_tolerance_sec=5.0,
    )

    assert decision.ok is False
    assert decision.reason_code == QUOTE_AGE_TIMESTAMP_MISMATCH
    assert decision.effective_age_sec == 600000.0
    assert decision.reported_age_sec == 1.0
    assert decision.timestamp_age_sec == 600000.0
    assert decision.mismatch_delta_sec == 599999.0


def test_quote_age_truth_accepts_matching_reported_and_timestamp_age():
    decision = classify_quote_age_truth(
        {
            "quote_ts_epoch": 1_700_000_000.0,
            "ts_epoch": 1_700_000_003.0,
            "quote_age_sec": 2.0,
        },
        mismatch_tolerance_sec=2.0,
    )

    assert decision.ok is True
    assert decision.reason_code == "ok"
    assert decision.effective_age_sec == 3.0


def test_candidate_freshness_blocks_timestamp_age_mismatch_for_executable_candidate():
    decision = classify_candidate_quote_freshness(
        _execution_candidate(
            quote_ts_epoch=1_700_000_000.0,
            ts_epoch=1_700_600_000.0,
            quote_age_sec=1.0,
            ltp_age_sec=1.0,
            bid_age_sec=1.0,
            ask_age_sec=1.0,
        )
    )

    assert decision.freshness_ok is False
    assert decision.reason_code == QUOTE_FRESHNESS_BLOCK_REASON
    assert QUOTE_AGE_TIMESTAMP_MISMATCH in decision.reasons
    assert decision.context["quote_age_truth"]["effective_age_sec"] == 600000.0


def test_candidate_freshness_uses_timestamp_effective_age_for_stale_detection():
    decision = classify_candidate_quote_freshness(
        _execution_candidate(
            quote_ts_epoch=1_700_000_000.0,
            ts_epoch=1_700_000_010.0,
            quote_age_sec=10.0,
            ltp_age_sec=10.0,
            bid_age_sec=10.0,
            ask_age_sec=10.0,
        )
    )

    assert decision.freshness_ok is False
    assert "stale_candidate_quote:quote_age_sec" in decision.reasons


def test_non_execution_candidate_does_not_block_on_quote_age_mismatch():
    payload = _execution_candidate(candidate_class="ADVISORY", execution_entry_status="non_executable")
    payload["quote_ts_epoch"] = 1_700_000_000.0
    payload["ts_epoch"] = 1_700_600_000.0
    payload["quote_age_sec"] = 1.0

    decision = classify_candidate_quote_freshness(payload)

    assert decision.freshness_ok is True
    assert decision.reason_code == "not_execution_capable"
