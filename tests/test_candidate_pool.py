from __future__ import annotations

from core.candidate_pool import build_candidate_pool, normalize_candidate


def _candidate(**overrides):
    row = {
        "trade_id": "T-POOL",
        "symbol": "NIFTY",
        "strategy": "UNIT",
        "opt_ltp": 120.0,
        "current_ltp": 120.0,
        "best_bid": 119.8,
        "best_ask": 120.2,
        "spread_pct": 0.0033,
        "liquidity_score": 0.82,
        "quote_age_sec": 0.4,
        "max_quote_age_sec": 2.0,
        "quote_source": "live_broker",
        "spread_source": "live_book",
        "liquidity_source": "live_book",
        "contract_exact_match": True,
        "execution_entry": 120.2,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "selected_for_execution": False,
        "final_score": 0.72,
    }
    row.update(overrides)
    return row


def test_normalize_candidate_marks_clean_execution_candidate_executable():
    normalized = normalize_candidate(_candidate(), index=0)

    assert normalized["candidate_lifecycle"] == "EXECUTABLE"
    assert normalized["candidate_status"] == "executable"
    assert normalized["execution_truth_allowed"] is True
    assert normalized["data_quality_grade"] == "A"


def test_normalize_candidate_marks_fallback_candidate_advisory_and_non_executable():
    normalized = normalize_candidate(
        _candidate(
            phase2_spread_fallback_used=True,
            spread_source="fallback_default",
            selected_for_execution=True,
        ),
        index=0,
    )

    assert normalized["candidate_lifecycle"] == "ADVISORY_ONLY"
    assert normalized["candidate_status"] == "advisory_only"
    assert normalized["execution_truth_allowed"] is False
    assert normalized["execution_allowed"] is False
    assert normalized["eligible_for_execution"] is False
    assert normalized["selected_for_execution"] is False
    assert normalized["capital_assigned"] == 0.0


def test_candidate_pool_separates_executable_advisory_and_rejected_streams():
    pool = build_candidate_pool(
        [
            _candidate(trade_id="T-EXEC", final_score=0.71),
            _candidate(
                trade_id="T-ADV",
                final_score=0.95,
                phase2_liquidity_fallback_used=True,
                liquidity_source="fallback_default",
            ),
            _candidate(trade_id="T-REJECT", final_score=0.10, reject_reason="unit_reject"),
        ]
    )

    assert pool.counts["total"] == 3
    assert [row["trade_id"] for row in pool.top_executable_candidates] == ["T-EXEC"]
    assert [row["trade_id"] for row in pool.advisory_candidates] == ["T-ADV"]
    assert [row["trade_id"] for row in pool.rejected_candidates] == ["T-REJECT"]


def test_high_scoring_dirty_candidate_does_not_enter_executable_stream():
    pool = build_candidate_pool(
        [
            _candidate(trade_id="T-CLEAN", final_score=0.60),
            _candidate(
                trade_id="T-DIRTY-HIGH",
                final_score=0.99,
                quote_source="unknown",
            ),
        ]
    )

    assert [row["trade_id"] for row in pool.top_executable_candidates] == ["T-CLEAN"]
    assert [row["trade_id"] for row in pool.advisory_candidates] == ["T-DIRTY-HIGH"]


def test_pool_assigns_candidate_pool_rank_only_to_executable_rows():
    pool = build_candidate_pool(
        [
            _candidate(trade_id="T-LOW", final_score=0.61),
            _candidate(trade_id="T-HIGH", final_score=0.82),
            _candidate(
                trade_id="T-ADV",
                final_score=0.99,
                phase2_spread_fallback_used=True,
                spread_source="fallback_default",
            ),
        ]
    )

    assert [(row["trade_id"], row["candidate_pool_rank"]) for row in pool.top_executable_candidates] == [
        ("T-HIGH", 1),
        ("T-LOW", 2),
    ]
    assert "candidate_pool_rank" not in pool.advisory_candidates[0]
