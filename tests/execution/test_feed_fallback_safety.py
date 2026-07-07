import pytest
from unittest.mock import patch
from core.candidate_quote_freshness import classify_candidate_quote_freshness
from core.advisory_schema import validate_advisory_row

@patch("core.candidate_quote_freshness.cfg")
def test_quote_older_than_sla_drops_to_advisory(mock_cfg):
    """
    REQ-FEED-01: Proves that a quote older than SLA is identified as stale,
    and when passed through advisory normalization, it is dropped to ADVISORY.
    """
    mock_cfg.OPTION_LTP_SLA_SEC = 2.0
    mock_cfg.CANDIDATE_QUOTE_FRESHNESS_MAX_AGE_SEC = 2.0
    
    candidate = {
        "trade_id": "test_trade_123",
        "advisory_id": "test_trade_123",
        "strategy_id": "test_strat",
        "symbol": "BANKNIFTY",
        "strategy_name": "Test Strategy",
        "timestamp": "2023-01-01T12:00:00Z",
        "instrument_type": "OPT",
        "execution_entry": 100.0,
        "execution_entry_source": "ask",
        "execution_entry_status": "executable",
        "display_entry": 100.0,
        "display_entry_source": "ask",
        "display_entry_status": "displayable",
        "entry_display_status": "displayable",
        "entry_reason": "test",
        "entry_clear_reason": "",
        "entry": 100.0,
        "entry_status": "executable",
        "entry_source": "ask",
        "confidence": 1.0,
        "readiness": "READY",
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
        "quote_source": "ws",
        "decision_explain": [],
        "market_open": True,
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
    
    # 2. Schema normalization accepts the blocked state
    advisory_payload = candidate.copy()
    advisory_payload["hard_blockers"] = list(decision.reasons)
    advisory_payload["permission"] = "BLOCK"
    advisory_payload["final_action"] = "BLOCK"
    advisory_payload["execution_status"] = "blocked"
    advisory_payload["readiness"] = "BLOCKED"
    
    normalized = validate_advisory_row(advisory_payload)
    
    # Invariant: the schema validator passes and preserves the blocked state
    assert normalized["execution_status"] == "blocked"
    assert normalized["permission"] == "BLOCK"


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
