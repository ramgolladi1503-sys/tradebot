import pytest
from core.review_queue import _normalize_truth_quality

def test_truth_live_fresh_execute():
    out = {
        "final_action": "EXECUTE",
        "truth_quality": "LIVE"
    }
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_LIVE_FRESH"
    assert res["truth_allows_execution"] is True
    assert res["final_action"] == "EXECUTE"

def test_truth_degraded_allowed_execute():
    out = {
        "final_action": "EXECUTE",
        "truth_quality": "DEGRADED"
    }
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_DEGRADED_ALLOWED"
    assert res["truth_allows_execution"] is True
    assert res["final_action"] == "EXECUTE"

def test_truth_degraded_blocked_queue_only():
    out = {
        "final_action": "QUEUE_ONLY",
        "truth_quality": "DEGRADED"
    }
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_DEGRADED_BLOCKED"
    assert res["truth_allows_execution"] is False

def test_truth_fallback_blocked():
    out = {
        "final_action": "EXECUTE",
        "row_kind": "fallback"
    }
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_FALLBACK_BLOCKED"
    assert res["truth_allows_execution"] is False
    # Enforces downgrade!
    assert res["final_action"] == "REJECT"

def test_truth_recovered_fallback_blocked():
    out = {
        "final_action": "QUEUE_ONLY",
        "is_recovered_fallback": True
    }
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_FALLBACK_BLOCKED"
    assert res["truth_allows_execution"] is False

def test_truth_synthetic_blocked():
    out = {
        "final_action": "EXECUTE",
        "is_synthetic": True
    }
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_SYNTHETIC_BLOCKED"
    assert res["truth_allows_execution"] is False
    assert res["final_action"] == "REJECT"

def test_truth_stale_blocked():
    out = {
        "final_action": "EXECUTE",
        "stale_quote_flag": True
    }
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_STALE_BLOCKED"
    assert res["truth_allows_execution"] is False
    assert res["final_action"] == "REJECT"

def test_truth_unknown_blocked():
    out = {
        "final_action": "QUEUE_ONLY",
        "truth_quality": None
    }
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_UNKNOWN_BLOCKED"
    assert res["truth_allows_execution"] is False

def test_truth_execute_implies_live_fresh_if_missing():
    out = {
        "final_action": "EXECUTE",
        "truth_quality": None
    }
    # It assumes live if it reached execute (unless blocked state flags exist)
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_LIVE_FRESH"
    assert res["truth_allows_execution"] is True
    assert res["final_action"] == "EXECUTE"
