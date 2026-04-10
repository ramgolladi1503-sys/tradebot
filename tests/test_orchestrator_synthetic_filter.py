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
    assert soft[0]["execution_status"] == "scored"
    assert soft[0]["candidate_status"] == "near_executable"
    assert soft[0]["eligible_for_execution"] is True
    assert soft[0]["execution_blocked"] is False
    assert _is_synthetic_candidate(soft[0]) is False
    assert _candidate_visibility_bucket(soft[0]) == "executable"
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


def test_near_executable_with_hard_contract_issue_is_not_promoted():
    candidate = {
        "trade_id": "tbsoft_NIFTY_999",
        "candidate_origin": "softened_builder_path",
        "candidate_type": "directional",
        "strategy_family": "breakout",
        "candidate_status": "near_executable",
        "execution_status": "scored",
        "permission": "QUEUE_ONLY",
        "final_action": "QUEUE_ONLY",
        "readiness": "QUEUE_ONLY",
        "unresolved_contract": True,
    }

    assert _candidate_visibility_bucket(candidate) == "blocked"


def test_soft_reject_with_hard_reason_stays_advisory_only():
    class _BuilderStub:
        _reject_ctx = {"reason": "feed_stale", "gate_reasons": ["feed_stale"]}

    ranked, soft, reason, gates = _augment_ranked_candidates_with_soft_reject(
        trade_builder=_BuilderStub(),
        ranked_candidates=[],
        market_data={"symbol": "NIFTY"},
        execution_mode="LIVE",
        symbol="NIFTY",
    )

    assert reason == "feed_stale"
    assert gates == ["feed_stale"]
    assert len(soft) == 1
    assert soft[0]["execution_status"] == "advisory_only"
    assert soft[0]["candidate_status"] == "advisory_only"
    assert soft[0]["eligible_for_execution"] is False
    assert soft[0]["execution_blocked"] is True
    assert ranked and ranked[0]["trade_id"] == soft[0]["trade_id"]
