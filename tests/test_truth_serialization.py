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

def test_missing_truth_execute_is_unknown_blocked():
    out = {
        "final_action": "EXECUTE",
        "truth_quality": None
    }
    res = _normalize_truth_quality(out)
    assert res["truth_quality"] == "TRUTH_UNKNOWN_BLOCKED"
    assert res["truth_allows_execution"] is False
    assert res["final_action"] == "REJECT"
    assert res.get("promotion_block_reason", "").startswith("truth_violation")

def test_artifact_level_validation():
    # Simulate rows passed through _finalize_append_payload_for_runtime_write
    rows = [
        {"final_action": "EXECUTE", "truth_quality": "LIVE"},
        {"final_action": "EXECUTE", "truth_quality": "DEGRADED"},
        {"final_action": "QUEUE_ONLY", "truth_quality": None},
        {"final_action": "EXECUTE", "stale_quote_flag": True},
        {"final_action": "EXECUTE", "is_synthetic": True},
    ]

    validated = [_normalize_truth_quality(dict(r)) for r in rows]

    for row in validated:
        assert row.get("truth_quality") is not None

        if row.get("final_action") == "EXECUTE":
            assert row["truth_quality"] in {"TRUTH_LIVE_FRESH", "TRUTH_DEGRADED_ALLOWED"}
            assert row["truth_allows_execution"] is True
        else:
            if row["truth_quality"] in {"TRUTH_FALLBACK_BLOCKED", "TRUTH_SYNTHETIC_BLOCKED", "TRUTH_STALE_BLOCKED", "TRUTH_UNKNOWN_BLOCKED"}:
                assert row["truth_allows_execution"] is False

        if row["truth_quality"] == "TRUTH_UNKNOWN_BLOCKED":
            assert row.get("final_action") != "EXECUTE"
