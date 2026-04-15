from core.review_queue import (
    _apply_candidate_identity,
    _best_reject_reason,
    _classify_candidate_status,
    _finalize_append_payload_for_runtime_write,
    _is_execution_eligible,
)


def test_synthetic_advisory_strategy_not_remapped():
    row = {
        "trade_id": "softrej_123",
        "symbol": "NIFTY",
        "candidate_type": "fallback_market_candidate",
        "permission": "ADVISORY_ONLY",
        "final_action": "ADVISORY_ONLY",
    }
    out = _apply_candidate_identity(row)
    assert out["strategy_family"] == "synthetic_advisory"
    assert out["setup_variant"] == "synthetic_advisory"
    assert out["execution_status"] == "advisory_only"
    assert out["candidate_status"] == "advisory_only"
    assert out["eligible_for_execution"] is False

    finalized = _finalize_append_payload_for_runtime_write(out)
    assert finalized["strategy_family"] == "synthetic_advisory"
    assert finalized["setup_variant"] == "synthetic_advisory"


def test_execution_eligibility_excludes_synthetic_and_allows_near_executable():
    synthetic = {
        "strategy_family": "synthetic_advisory",
        "execution_status": "scored",
        "candidate_status": "near_executable",
        "eligible_for_execution": True,
    }
    real = {
        "strategy_family": "breakout",
        "execution_status": "scored",
        "candidate_status": "near_executable",
        "eligible_for_execution": True,
    }
    assert _is_execution_eligible(synthetic) is False
    assert _is_execution_eligible(real) is True


def test_execution_eligibility_excludes_recovered_fallback_source():
    recovered = {
        "strategy_family": "breakout",
        "execution_entry_source": "recovered_fallback",
        "execution_status": "scored",
        "candidate_status": "near_executable",
        "eligible_for_execution": True,
    }
    assert _is_execution_eligible(recovered) is False


def test_classify_candidate_status_softened_non_executable_forces_advisory():
    row = {
        "trade_id": "tbsoft_123",
        "candidate_origin": "softened_builder_path",
        "execution_entry_status": "non_executable",
        "execution_status": "queue_only",
        "permission": "QUEUE_ONLY",
        "final_action": "QUEUE_ONLY",
        "readiness": "QUEUE_ONLY",
        "rank_score": 0.42,
        "confidence_final": 0.41,
    }
    out = _classify_candidate_status(row)
    assert out["candidate_status"] == "advisory_only"
    assert out["eligible_for_execution"] is False
    assert out["execution_allowed"] is False
    assert out["is_executable"] is False


def test_best_reject_reason_prefers_specific_reason_over_unspecified():
    row = {
        "reason": "unspecified_trade_builder_reject",
        "reject_reason": "unspecified_trade_builder_reject",
        "entry_block_code": "unspecified_trade_builder_reject",
        "final_blocker": "unresolved_contract",
    }
    assert _best_reject_reason(row) == "unresolved_contract"
