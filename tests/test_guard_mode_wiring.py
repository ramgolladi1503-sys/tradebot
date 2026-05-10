from __future__ import annotations

import pytest

from core.candidate_finalization import assert_executable_candidate_ready, mirror_candidate_truth
from core.capital_allocator import allocate_capital_slots


def _candidate(**overrides):
    row = {
        "trade_id": "T-GUARD",
        "symbol": "NIFTY",
        "strategy_family": "unit",
        "confidence": 0.75,
        "rank_score": 0.75,
        "candidate_status": "executable",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_status": "executable",
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
        "execution_allowed": True,
        "eligible_for_execution": True,
        "selected_for_execution": True,
        "tradable": True,
        "capital_at_risk": 120.2,
        "size_mult": 1.0,
    }
    row.update(overrides)
    return row


def test_mirror_candidate_truth_preserves_clean_executable_candidate():
    out = mirror_candidate_truth(_candidate())

    assert out["execution_truth_allowed"] is True
    assert out["data_quality_grade"] == "A"
    assert out["execution_allowed"] is True
    assert out["selected_for_execution"] is True
    assert out["source_flags"]["data_truth_guard_applied"] is False


def test_mirror_candidate_truth_downgrades_dirty_fallback_candidate():
    out = mirror_candidate_truth(
        _candidate(
            phase2_spread_fallback_used=True,
            spread_source="fallback_default",
        )
    )

    assert out["execution_truth_allowed"] is False
    assert out["data_quality_grade"] == "D"
    assert out["execution_allowed"] is False
    assert out["eligible_for_execution"] is False
    assert out["selected_for_execution"] is False
    assert out["capital_assigned"] == 0.0
    assert out["candidate_status"] == "advisory_only"
    assert "fallback_spread" in out["execution_truth_blockers"]
    assert out["source_flags"]["data_truth_guard_applied"] is True


def test_assert_executable_candidate_ready_rejects_dirty_executable_candidate():
    with pytest.raises(AssertionError, match="failed data truth"):
        assert_executable_candidate_ready(
            _candidate(
                phase2_liquidity_fallback_used=True,
                liquidity_source="fallback_default",
            )
        )


def test_assert_executable_candidate_ready_accepts_clean_candidate():
    assert_executable_candidate_ready(_candidate())


def test_capital_allocator_blocks_dirty_selected_candidate():
    allocated = allocate_capital_slots(
        [
            _candidate(
                trade_id="T-DIRTY-ALLOC",
                final_score=0.95,
                phase2_spread_fallback_used=True,
                spread_source="fallback_default",
            )
        ],
        max_slots=1,
        per_symbol_cap=1,
        per_theme_cap=1,
        capital_budget_cap=1000.0,
        minimum_quality_threshold=0.1,
        replacement_enabled=True,
        replacement_min_delta=0.01,
    )

    row = allocated[0]
    assert row["selected_for_execution"] is False
    assert row["capital_assigned"] == 0.0
    assert row["size_multiplier_effective"] == 0.0
    assert row["allocation_reason"].startswith("data_truth_block:D")
    assert row["selection_reason"] == "allocation_data_truth_block"


def test_capital_allocator_allows_clean_selected_candidate():
    allocated = allocate_capital_slots(
        [_candidate(trade_id="T-CLEAN-ALLOC", final_score=0.80)],
        max_slots=1,
        per_symbol_cap=1,
        per_theme_cap=1,
        capital_budget_cap=1000.0,
        minimum_quality_threshold=0.1,
        replacement_enabled=True,
        replacement_min_delta=0.01,
    )

    row = allocated[0]
    assert row["selected_for_execution"] is True
    assert row["capital_assigned"] > 0
    assert row["allocation_reason"] == "allocated"
    assert row["data_quality_grade"] == "A"
