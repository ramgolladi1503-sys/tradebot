from __future__ import annotations

from core.guarded_review import enforce_review_data_truth


def _entry(**overrides):
    row = {
        "trade_id": "T-REVIEW-GUARD",
        "symbol": "NIFTY",
        "opt_ltp": 120.0,
        "current_ltp": 120.0,
        "best_bid": 119.8,
        "best_ask": 120.2,
        "spread_pct": 0.003,
        "liquidity_score": 0.82,
        "quote_age_sec": 0.3,
        "max_quote_age_sec": 2.0,
        "quote_source": "live_broker",
        "spread_source": "live_book",
        "liquidity_source": "live_book",
        "contract_exact_match": True,
        "execution_entry": 120.2,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "execution_status": "executable",
        "candidate_status": "executable",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "selected_for_execution": True,
        "tradable": True,
    }
    row.update(overrides)
    return row


def test_review_guard_preserves_clean_execution_entry():
    out = enforce_review_data_truth(_entry())

    assert out["execution_truth_allowed"] is True
    assert out["review_data_truth_guard_applied"] is False
    assert out["permission"] == "EXECUTE"
    assert out["final_action"] == "EXECUTE"
    assert out["execution_allowed"] is True


def test_review_guard_blocks_dirty_execution_claim():
    out = enforce_review_data_truth(
        _entry(
            phase2_spread_fallback_used=True,
            spread_source="fallback_default",
        )
    )

    assert out["execution_truth_allowed"] is False
    assert out["review_data_truth_guard_applied"] is True
    assert out["permission"] == "BLOCK"
    assert out["final_action"] == "BLOCK"
    assert out["readiness"] == "BLOCKED"
    assert out["execution_status"] == "blocked"
    assert out["candidate_status"] == "blocked"
    assert out["execution_allowed"] is False
    assert out["eligible_for_execution"] is False
    assert out["selected_for_execution"] is False
    assert out["capital_assigned"] == 0.0
    assert "fallback_spread" in out["gates_failed"]


def test_review_guard_keeps_non_execution_dirty_entry_advisory():
    out = enforce_review_data_truth(
        _entry(
            permission="QUEUE_ONLY",
            final_action="QUEUE_ONLY",
            execution_status="queue_only",
            candidate_status="advisory_only",
            execution_allowed=False,
            eligible_for_execution=False,
            selected_for_execution=False,
            phase2_liquidity_fallback_used=True,
            liquidity_source="fallback_default",
        )
    )

    assert out["execution_truth_allowed"] is False
    assert out["permission"] == "ADVISORY_ONLY"
    assert out["final_action"] == "ADVISORY_ONLY"
    assert out["execution_status"] == "advisory_only"
    assert out["candidate_status"] == "advisory_only"
    assert "fallback_liquidity" in out["gates_failed"]
