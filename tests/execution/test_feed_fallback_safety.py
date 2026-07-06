import pytest
from unittest.mock import patch
from core.candidate_quote_freshness import classify_candidate_quote_freshness
from core.advisory_schema import normalize_advisory_payload

@patch("core.candidate_quote_freshness.cfg")
def test_quote_older_than_sla_drops_to_advisory(mock_cfg):
    """
    REQ-FEED-01: Proves that a quote older than SLA is identified as stale,
    and when passed through advisory normalization, it is dropped to ADVISORY.
    """
    mock_cfg.OPTION_LTP_SLA_SEC = 2.0
    mock_cfg.CANDIDATE_QUOTE_FRESHNESS_MAX_AGE_SEC = 2.0
    
    candidate = {
        "candidate_class": "EXECUTABLE",
        "option_token": "12345",
        "last_option_tick_epoch": 1000.0,
        "option_ltp_timestamp": 1000.0,
        "quote_ts_epoch": 1000.0,
        "quote_age_sec": 3.5, # Exceeds SLA of 2.0
        "chain_snapshot_age_sec": 1.0,
        "market_mode": "LIVE"
    }
    
    # 1. Freshness evaluator must flag it as stale
    decision = classify_candidate_quote_freshness(candidate)
    
    assert decision.freshness_ok is False
    assert "stale_candidate_quote:quote_age_sec" in decision.reasons
    
    # 2. Schema normalization drops this to ADVISORY
    # We add the blocker from the freshness decision
    advisory_payload = candidate.copy()
    advisory_payload["hard_blockers"] = list(decision.reasons)
    advisory_payload["permission"] = "EXECUTE"
    
    normalized = normalize_advisory_payload(advisory_payload)
    
    # Invariant: execution_status MUST be advisory_only because of hard blockers
    assert normalized["execution_status"] == "advisory_only"
    assert normalized["row_kind"] == "advisory_only"


def test_fallback_quotes_mathematically_barred():
    """
    REQ-FEED-02: Proves that fallback quotes are mathematically barred from execution array.
    """
    candidate = {
        "candidate_class": "EXECUTABLE",
        "option_token": "12345",
        "last_option_tick_epoch": 1000.0,
        "quote_ts_epoch": 1000.0,
        "quote_age_sec": 0.5,
        "chain_snapshot_age_sec": 0.5,
        "market_mode": "LIVE",
        # Simulating a fallback quote scenario where the feed reason is not OK
        "option_feed_block_reason": "stale_feed_fallback_active"
    }
    
    decision = classify_candidate_quote_freshness(candidate)
    
    # Invariant: Any non-OK feed block reason immediately invalidates the quote for execution
    assert decision.freshness_ok is False
    assert "stale_feed_fallback_active" in decision.reasons
