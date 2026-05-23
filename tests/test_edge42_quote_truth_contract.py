from __future__ import annotations

from core.executable_truth import (
    FALLBACK_DRIVEN_REASON,
    PRICE_MISMATCH_REASON,
    STALE_OPTION_LTP_REASON,
    SUBSCRIPTION_FAILED_REASON,
    classify_executable_truth,
)
from core.quote_age_truth import QUOTE_AGE_TIMESTAMP_MISMATCH
from core.quote_truth import (
    QUOTE_PRICE_MISMATCH_REASON,
    QUOTE_SOURCE_FALLBACK_REASON,
    QUOTE_SOURCE_SUBSCRIPTION_FAILED_REASON,
    QUOTE_STALE_REASON,
    classify_quote_truth,
)


def _candidate(**overrides):
    payload = {
        "candidate_class": "EXECUTABLE",
        "execution_entry_status": "executable",
        "instrument_token": 12345,
        "quote_source": "live",
        "option_ltp_source": "live",
        "current_ltp": 100.0,
        "best_bid": 99.5,
        "best_ask": 100.5,
        "quote_ts_epoch": 1_700_000_000.0,
        "ts_epoch": 1_700_000_001.0,
        "quote_age_sec": 1.0,
        "ltp_age_sec": 1.0,
        "bid_age_sec": 1.0,
        "ask_age_sec": 1.0,
        "chain_snapshot_age_sec": 1.0,
        "option_feed_block_reason": "OK",
        "market_mode": "LIVE",
        "signal_valid": True,
        "signal_strength": 0.7,
        "spread_ok": True,
        "liquidity_ok": True,
        "data_confidence": 0.9,
    }
    payload.update(overrides)
    return payload


def test_quote_truth_allows_fresh_live_quote():
    decision = classify_quote_truth(_candidate(), require_source=True, require_age=True)

    assert decision.truth_ok is True
    assert decision.rank_eligible is True
    assert decision.execution_eligible is True
    assert decision.source_trust == "trusted_live"
    assert decision.quote_validation_status == "OK"
    assert decision.effective_age_sec == 1.0
    assert decision.reasons == ()


def test_quote_truth_blocks_rest_fallback_source():
    decision = classify_quote_truth(
        _candidate(quote_source="rest_fallback", option_ltp_source="rest_fallback"),
        require_source=True,
        require_age=True,
    )

    assert decision.truth_ok is False
    assert decision.rank_eligible is False
    assert decision.execution_eligible is False
    assert decision.source_trust == "fallback"
    assert QUOTE_SOURCE_FALLBACK_REASON in decision.reasons


def test_quote_truth_blocks_subscription_failed_source():
    decision = classify_quote_truth(
        _candidate(quote_source="subscription_failed", option_ltp_source="subscription_failed"),
        require_source=True,
        require_age=True,
    )

    assert decision.truth_ok is False
    assert decision.source_trust == "subscription_failed"
    assert QUOTE_SOURCE_SUBSCRIPTION_FAILED_REASON in decision.reasons


def test_quote_truth_blocks_price_mismatch():
    decision = classify_quote_truth(
        _candidate(current_ltp=180.0, best_bid=99.5, best_ask=100.5),
        require_source=True,
        require_age=True,
    )

    assert decision.truth_ok is False
    assert decision.quote_validation_status == "PRICE_MISMATCH"
    assert QUOTE_PRICE_MISMATCH_REASON in decision.reasons


def test_quote_truth_blocks_timestamp_age_mismatch_and_effective_stale_age():
    decision = classify_quote_truth(
        _candidate(
            quote_ts_epoch=1_700_000_000.0,
            ts_epoch=1_700_600_000.0,
            quote_age_sec=1.0,
            ltp_age_sec=1.0,
            bid_age_sec=1.0,
            ask_age_sec=1.0,
        ),
        require_source=True,
        require_age=True,
    )

    assert decision.truth_ok is False
    assert decision.effective_age_sec == 600000.0
    assert QUOTE_AGE_TIMESTAMP_MISMATCH in decision.reasons
    assert QUOTE_STALE_REASON in decision.reasons


def test_executable_truth_uses_canonical_quote_truth_for_fallback_block():
    decision = classify_executable_truth(
        _candidate(quote_source="rest_fallback", option_ltp_source="rest_fallback")
    )

    assert decision.execution_allowed is False
    assert FALLBACK_DRIVEN_REASON in decision.reasons
    assert decision.context["quote_truth"]["source_trust"] == "fallback"
    assert QUOTE_SOURCE_FALLBACK_REASON in decision.context["quote_truth"]["reasons"]


def test_executable_truth_uses_canonical_quote_truth_for_subscription_failure():
    decision = classify_executable_truth(
        _candidate(quote_source="subscription_failed", option_ltp_source="subscription_failed")
    )

    assert decision.execution_allowed is False
    assert SUBSCRIPTION_FAILED_REASON in decision.reasons
    assert decision.context["quote_truth"]["source_trust"] == "subscription_failed"


def test_executable_truth_uses_canonical_quote_truth_for_price_mismatch():
    decision = classify_executable_truth(
        _candidate(current_ltp=180.0, best_bid=99.5, best_ask=100.5)
    )

    assert decision.execution_allowed is False
    assert PRICE_MISMATCH_REASON in decision.reasons
    assert decision.context["quote_truth"]["quote_validation_status"] == "PRICE_MISMATCH"


def test_executable_truth_uses_canonical_quote_truth_for_stale_timestamp():
    decision = classify_executable_truth(
        _candidate(
            quote_ts_epoch=1_700_000_000.0,
            ts_epoch=1_700_600_000.0,
            quote_age_sec=1.0,
            ltp_age_sec=1.0,
            bid_age_sec=1.0,
            ask_age_sec=1.0,
        )
    )

    assert decision.execution_allowed is False
    assert STALE_OPTION_LTP_REASON in decision.reasons
    assert QUOTE_AGE_TIMESTAMP_MISMATCH in decision.context["quote_truth"]["reasons"]
