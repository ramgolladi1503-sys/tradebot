from core.review_queue import _apply_candidate_identity, _finalize_append_payload_for_runtime_write


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

    finalized = _finalize_append_payload_for_runtime_write(out)
    assert finalized["strategy_family"] == "synthetic_advisory"
    assert finalized["setup_variant"] == "synthetic_advisory"
