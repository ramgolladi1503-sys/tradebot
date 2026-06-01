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


def test_indicators_missing_surfaces_when_phase2_starved_and_feed_fresh():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={"phase2_input_candidate_count": 0},
        phase2_rejection={},
        feed_truth={"market_closed_detected": False, "feed_fresh": True, "option_tick_fresh": True},
        top_opportunities={"phase2_state": "NO_TRADE"},
        cycle_blockers={"INDICATORS_MISSING": 3},
    )
    assert payload["primary_reason"] == "indicators_missing"
    assert payload["primary_reason_source"] == "cycle_blockers"
    assert payload["upstream_gate_reason_counts"].get("INDICATORS_MISSING") == 3
    assert "indicators_missing" in payload["supporting_reasons"]


def test_regime_unstable_surfaces_when_phase2_starved_and_feed_fresh():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={"phase2_input_candidate_count": 0},
        phase2_rejection={},
        feed_truth={"market_closed_detected": False, "feed_fresh": True, "option_tick_fresh": True},
        top_opportunities={"phase2_state": "NO_TRADE"},
        cycle_blockers={"REGIME_UNSTABLE": 1},
    )
    assert payload["primary_reason"] == "regime_unstable"
    assert payload["primary_reason_source"] == "cycle_blockers"
    assert payload["upstream_gate_reason_counts"].get("REGIME_UNSTABLE") == 1
    assert "regime_unstable" in payload["supporting_reasons"]


def test_feed_stale_outranks_indicators_missing_when_both_present():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={"phase2_input_candidate_count": 0},
        phase2_rejection={},
        feed_truth={"market_closed_detected": False, "feed_fresh": False, "option_tick_fresh": False},
        top_opportunities={"phase2_state": "NO_TRADE"},
        cycle_blockers={"INDICATORS_MISSING": 2},
    )
    assert payload["primary_reason"] == "feed_stale"


def test_market_closed_outranks_all_other_reasons():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={"phase2_input_candidate_count": 0},
        phase2_rejection={},
        feed_truth={"market_closed_detected": True, "feed_fresh": False, "option_tick_fresh": False},
        top_opportunities={"phase2_state": "NO_TRADE"},
        cycle_blockers={"INDICATORS_MISSING": 2, "REGIME_UNSTABLE": 1},
    )
    assert payload["primary_reason"] == "market_closed"


def test_indicator_details_are_emitted_when_runtime_evidence_present():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={"phase2_input_candidate_count": 0},
        phase2_rejection={},
        feed_truth={"market_closed_detected": False, "feed_fresh": True, "option_tick_fresh": True},
        top_opportunities={"phase2_state": "NO_TRADE"},
        cycle_blockers={"INDICATORS_MISSING": 1},
        indicator_readiness={
            "by_symbol": {
                "NIFTY": {
                    "symbol": "NIFTY",
                    "ohlc_bars_count": 12,
                    "warmup_min_bars": 50,
                    "indicator_missing_inputs": ["vwap", "rsi"],
                }
            }
        },
    )
    assert payload["indicator_detail_available"] is True
    assert payload["missing_indicators_by_symbol"]["NIFTY"]["symbol"] == "NIFTY"
    assert payload["warmup_candle_counts_by_symbol"]["NIFTY"] == 12
    assert payload["required_warmup_candle_counts_by_symbol"]["NIFTY"] == 50
    assert payload["missing_indicator_counts"]["vwap"] == 1
    assert payload["missing_indicator_counts"]["rsi"] == 1
    for k in (
        "missing_indicators_by_strategy",
        "indicator_ready_by_symbol",
        "indicator_ready_by_strategy",
        "indicator_age_sec_by_symbol",
        "indicator_source_by_symbol",
        "indicator_blocker_reason_counts",
    ):
        assert k in payload


def test_regime_details_are_emitted_when_truth_present():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={"phase2_input_candidate_count": 0},
        phase2_rejection={},
        feed_truth={"market_closed_detected": False, "feed_fresh": True, "option_tick_fresh": True},
        top_opportunities={"phase2_state": "NO_TRADE"},
        cycle_blockers={"REGIME_UNSTABLE": 1},
        regime_truth={
            "gate_reasons": {"REGIME_UNSTABLE": 1},
            "by_symbol": {
                "BANKNIFTY": {
                    "primary_regime": "RANGE",
                    "regime_entropy": 1.45,
                    "regime_prob_max": 0.38,
                    "unstable_reasons": ["entropy_too_high", "prob_too_low"],
                }
            },
        },
    )
    assert payload["regime_detail_available"] is True
    assert payload["regime_gate_reasons"]["REGIME_UNSTABLE"] == 1
    assert payload["regime_by_symbol"]["BANKNIFTY"]["primary_regime"] == "RANGE"


def test_indicator_schema_is_explicit_even_when_detail_missing():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={"phase2_input_candidate_count": 0},
        phase2_rejection={},
        feed_truth={"market_closed_detected": False, "feed_fresh": True, "option_tick_fresh": True},
        top_opportunities={"phase2_state": "NO_TRADE"},
        cycle_blockers={"INDICATORS_MISSING": 1},
        indicator_readiness=None,
    )
    assert payload["indicator_detail_available"] is False
    assert payload["indicator_detail_missing_reason"]
    assert isinstance(payload["missing_indicator_counts"], dict)
    assert isinstance(payload["missing_indicators_by_symbol"], dict)
    assert isinstance(payload["warmup_candle_counts_by_symbol"], dict)
    assert isinstance(payload["required_warmup_candle_counts_by_symbol"], dict)
    assert payload["writer_schema_version"] == payload["schema_version"]
    assert payload["writer_name"] == "runtime_notrade_reason_truth"


def test_regime_schema_is_explicit_even_when_detail_missing():
    payload = build_notrade_reason_truth_payload(
        candidate_handoff={"phase2_input_candidate_count": 0},
        phase2_rejection={},
        feed_truth={"market_closed_detected": False, "feed_fresh": True, "option_tick_fresh": True},
        top_opportunities={"phase2_state": "NO_TRADE"},
        cycle_blockers={"REGIME_UNSTABLE": 1},
        regime_truth=None,
    )
    assert payload["regime_detail_available"] is False
    assert payload["regime_detail_missing_reason"]
    assert isinstance(payload["regime_gate_reasons"], dict)
    assert isinstance(payload["regime_by_symbol"], dict)
