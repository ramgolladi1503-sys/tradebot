from __future__ import annotations

from core.data_quality import apply_data_quality_contract, assess_candidate_data_quality


def _clean_candidate(**overrides):
    candidate = {
        "trade_id": "T-DQ-CLEAN",
        "symbol": "NIFTY",
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
        "selected_for_execution": True,
    }
    candidate.update(overrides)
    return candidate


def test_clean_live_candidate_is_execution_truth_allowed():
    result = assess_candidate_data_quality(_clean_candidate())

    assert result.data_quality_grade == "A"
    assert result.execution_truth_allowed is True
    assert result.execution_truth_blockers == []
    assert result.fallback_fields == []


def test_fallback_spread_blocks_execution_truth():
    candidate = _clean_candidate(
        phase2_spread_fallback_used=True,
        spread_source="fallback_default",
    )

    result = assess_candidate_data_quality(candidate)

    assert result.execution_truth_allowed is False
    assert result.data_quality_grade == "D"
    assert "spread_pct" in result.fallback_fields
    assert "fallback_spread" in result.execution_truth_blockers
    assert "dirty_spread_lineage" in result.execution_truth_blockers


def test_fallback_liquidity_blocks_execution_truth_even_with_high_score():
    candidate = _clean_candidate(
        final_score=0.95,
        phase2_liquidity_fallback_used=True,
        liquidity_source="fallback_default",
    )

    enriched = apply_data_quality_contract(candidate)

    assert enriched["execution_truth_allowed"] is False
    assert enriched["execution_allowed"] is False
    assert enriched["eligible_for_execution"] is False
    assert enriched["selected_for_execution"] is False
    assert enriched["capital_assigned"] == 0.0
    assert "fallback_liquidity" in enriched["execution_truth_blockers"]


def test_unknown_quote_source_blocks_execution_truth():
    result = assess_candidate_data_quality(_clean_candidate(quote_source="unknown"))

    assert result.execution_truth_allowed is False
    assert "unknown_quote_source" in result.execution_truth_blockers
    assert result.data_quality_grade == "D"


def test_stale_quote_blocks_execution_truth():
    result = assess_candidate_data_quality(_clean_candidate(quote_age_sec=5.0, max_quote_age_sec=2.0))

    assert result.execution_truth_allowed is False
    assert "stale_quote" in result.execution_truth_blockers


def test_missing_bid_ask_blocks_execution_truth():
    result = assess_candidate_data_quality(_clean_candidate(best_bid=None, best_ask=None))

    assert result.execution_truth_allowed is False
    assert result.data_quality_grade == "F"
    assert "missing_bid_ask" in result.execution_truth_blockers


def test_recovered_fallback_execution_entry_blocks_execution_truth():
    result = assess_candidate_data_quality(
        _clean_candidate(
            execution_entry_source="recovered_fallback",
            execution_entry_lineage="RECOVERED_FALLBACK",
        )
    )

    assert result.execution_truth_allowed is False
    assert "dirty_execution_entry_source" in result.execution_truth_blockers
    assert "dirty_execution_entry_lineage" in result.execution_truth_blockers


def test_existing_fallback_fields_for_execution_critical_values_block_execution():
    result = assess_candidate_data_quality(_clean_candidate(fallback_fields=["execution_entry", "spread_pct"]))

    assert result.execution_truth_allowed is False
    assert "fallback_execution_entry" in result.execution_truth_blockers
    assert "fallback_spread_pct" in result.execution_truth_blockers
