from core.review_queue import _apply_candidate_identity, _finalize_append_payload_for_runtime_write, _is_execution_eligible


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
