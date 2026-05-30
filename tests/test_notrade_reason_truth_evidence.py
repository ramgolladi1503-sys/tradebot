from __future__ import annotations

from core.runtime_notrade_reason_truth import build_notrade_reason_truth_payload


def test_missing_quote_age_surfaces_as_missing_quote_truth_primary():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={"phase2_input_candidate_count": 1},
        phase2_rejection={"missing_quote_age_count": 2},
        feed_truth={"market_closed_detected": False, "feed_fresh": True, "option_tick_fresh": True},
        top_opportunities={},
    )
    assert payload["primary_reason"] == "missing_quote_truth"
    assert "missing_quote_age" in payload["supporting_reasons"]


def test_feed_stale_outranks_score_below_threshold():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={},
        phase2_rejection={"feed_stale_hard_block_count": 1, "top_non_executable_reasons": {"score_below_threshold": 10}},
        feed_truth={"market_closed_detected": False, "feed_fresh": False, "option_tick_fresh": False},
        top_opportunities={},
    )
    assert payload["primary_reason"] == "feed_stale"


def test_unresolved_contract_outranks_generic_strategy_no_edge():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={},
        phase2_rejection={"unresolved_contract_hard_block_count": 3, "top_non_executable_reasons": {"no_signal": 5}},
        feed_truth={"market_closed_detected": False, "feed_fresh": True, "option_tick_fresh": True},
        top_opportunities={},
    )
    assert payload["primary_reason"] == "unresolved_contract"


def test_market_closed_is_primary_when_detected():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={},
        phase2_rejection={"missing_quote_age_count": 1, "feed_stale_hard_block_count": 1},
        feed_truth={"market_closed_detected": True, "feed_fresh": False, "option_tick_fresh": False},
        top_opportunities={},
    )
    assert payload["primary_reason"] == "market_closed"
    assert payload["primary_reason_source"] == "feed_truth_latest"


def test_fallback_surfaces_as_fallback_blocked():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={},
        phase2_rejection={"fallback_quote_count": 1, "recovered_fallback_count": 2},
        feed_truth={"market_closed_detected": False, "feed_fresh": True, "option_tick_fresh": True},
        top_opportunities={},
    )
    assert payload["primary_reason"] == "fallback_blocked"

