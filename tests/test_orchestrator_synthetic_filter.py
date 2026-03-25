from core.orchestrator import _augment_ranked_candidates_with_soft_reject, _is_synthetic_candidate


def test_is_synthetic_candidate_origin_and_permission():
    assert _is_synthetic_candidate({"candidate_origin": "pre_builder_gate"}) is True
    assert _is_synthetic_candidate({"candidate_origin": "fallback_min_breadth"}) is True
    assert _is_synthetic_candidate({"candidate_origin": "invalid_snapshot"}) is True
    assert _is_synthetic_candidate({"permission": "ADVISORY_ONLY", "final_action": "ADVISORY_ONLY"}) is True
    assert _is_synthetic_candidate({"candidate_origin": "strategy", "permission": "EXECUTE", "final_action": "EXECUTE"}) is False


def test_soft_reject_skipped_for_trend_vwap_fallback():
    class _BuilderStub:
        _reject_ctx = {"reason": "trend_vwap_fallback", "gate_reasons": ["trend_vwap_fallback"]}

    ranked, soft, reason, gates = _augment_ranked_candidates_with_soft_reject(
        trade_builder=_BuilderStub(),
        ranked_candidates=[{"trade_id": "cand_1"}],
        market_data={"symbol": "NIFTY"},
        execution_mode="SIM",
        symbol="NIFTY",
    )

    assert reason == "trend_vwap_fallback"
    assert gates == ["trend_vwap_fallback"]
    assert soft == []
    assert ranked and ranked[0]["trade_id"] == "cand_1"


def test_soft_reject_skipped_for_no_candidates_survived():
    class _BuilderStub:
        _reject_ctx = {"reason": "no_candidates_survived", "gate_reasons": ["no_candidates_survived"]}

    ranked, soft, reason, gates = _augment_ranked_candidates_with_soft_reject(
        trade_builder=_BuilderStub(),
        ranked_candidates=[{"trade_id": "cand_1"}],
        market_data={"symbol": "SENSEX"},
        execution_mode="SIM",
        symbol="SENSEX",
    )

    assert reason == "no_candidates_survived"
    assert gates == ["no_candidates_survived"]
    assert soft == []
    assert ranked and ranked[0]["trade_id"] == "cand_1"
