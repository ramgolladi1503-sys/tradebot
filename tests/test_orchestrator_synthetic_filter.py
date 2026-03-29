from core.orchestrator import (
    _augment_ranked_candidates_with_soft_reject,
    _candidate_visibility_bucket,
    _is_synthetic_candidate,
)


def test_is_synthetic_candidate_origin_and_permission():
    assert _is_synthetic_candidate({"candidate_origin": "pre_builder_gate"}) is True
    assert _is_synthetic_candidate({"candidate_origin": "fallback_min_breadth"}) is True
    assert _is_synthetic_candidate({"candidate_origin": "invalid_snapshot"}) is True
    assert _is_synthetic_candidate({"permission": "ADVISORY_ONLY", "final_action": "ADVISORY_ONLY"}) is False
    assert _is_synthetic_candidate({"trade_id": "softrej_NIFTY_1", "permission": "ADVISORY_ONLY", "final_action": "ADVISORY_ONLY"}) is True
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


def test_soft_reject_created_for_no_candidates_survived_in_sim():
    class _BuilderStub:
        _reject_ctx = {"reason": "no_candidates_survived", "gate_reasons": ["no_candidates_survived"]}

    ranked, soft, reason, gates = _augment_ranked_candidates_with_soft_reject(
        trade_builder=_BuilderStub(),
        ranked_candidates=[],
        market_data={"symbol": "SENSEX"},
        execution_mode="SIM",
        symbol="SENSEX",
    )

    assert reason == "no_candidates_survived"
    assert gates == ["no_candidates_survived"]
    assert len(soft) == 1
    assert soft[0]["trade_id"].startswith("tbsoft_SENSEX_")
    assert soft[0]["candidate_origin"] == "softened_builder_path"
    assert _is_synthetic_candidate(soft[0]) is False
    assert _candidate_visibility_bucket(soft[0]) == "advisory"
    assert ranked and ranked[0]["trade_id"] == soft[0]["trade_id"]


def test_soft_reject_skipped_for_no_candidates_survived_in_live():
    class _BuilderStub:
        _reject_ctx = {"reason": "no_candidates_survived", "gate_reasons": ["no_candidates_survived"]}

    ranked, soft, reason, gates = _augment_ranked_candidates_with_soft_reject(
        trade_builder=_BuilderStub(),
        ranked_candidates=[{"trade_id": "cand_1"}],
        market_data={"symbol": "SENSEX"},
        execution_mode="LIVE",
        symbol="SENSEX",
    )

    assert reason == "no_candidates_survived"
    assert gates == ["no_candidates_survived"]
    assert soft == []
    assert ranked and ranked[0]["trade_id"] == "cand_1"


def test_builder_path_advisory_candidate_is_not_synthetic():
    candidate = {
        "trade_id": "tbsoft_NIFTY_12345",
        "candidate_origin": "softened_builder_path",
        "candidate_type": "directional",
        "permission": "ADVISORY_ONLY",
        "final_action": "ADVISORY_ONLY",
        "execution_status": "advisory_only",
        "candidate_status": "advisory_only",
        "execution_allowed": False,
    }

    assert _is_synthetic_candidate(candidate) is False
    assert _candidate_visibility_bucket(candidate) == "advisory"
