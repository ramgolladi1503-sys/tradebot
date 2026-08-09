import strategies.ensemble as ensemble


def _child(strategy_id, direction, score, confidence=0.8, sha="abc123"):
    return {
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "reason": strategy_id,
        "source_strategy_id": strategy_id,
        "source_sha256": sha,
        "structural_status": "STRUCTURALLY_VALID",
        "evidence": {"freshness_valid": True, "contract_valid": True},
    }


def test_ensemble_requires_proven_child_signals_and_never_synthesizes_alpha():
    assert ensemble.ensemble_signal({"regime": "TREND", "ltp": 102.0, "vwap": 100.0}) is None

    signal = ensemble.ensemble_signal({
        "child_signals": [
            _child("opening_range_retest", "BUY_CALL", 0.78, sha="orbsha"),
            _child("trend_pullback", "BUY_CALL", 0.70, sha="tpsha"),
        ]
    })
    assert signal is not None
    assert signal.direction == "BUY_CALL"
    assert signal.source_strategy_id == "ensemble"
    assert signal.structural_status == "STRUCTURALLY_VALID"
    assert signal.evidence["child_strategy_ids"] == ("opening_range_retest", "trend_pullback")


def test_ensemble_fails_closed_on_missing_or_invalid_provenance():
    missing_hash = _child("trend_pullback", "BUY_CALL", 0.8)
    missing_hash["source_sha256"] = ""
    assert ensemble.ensemble_signal({"child_signals": [missing_hash]}) is None

    stale = _child("trend_pullback", "BUY_CALL", 0.8)
    stale["evidence"]["freshness_valid"] = False
    assert ensemble.ensemble_signal({"child_signals": [stale]}) is None

    unvalidated = _child("trend_pullback", "BUY_CALL", 0.8)
    unvalidated["structural_status"] = "UNKNOWN"
    assert ensemble.ensemble_signal({"child_signals": [unvalidated]}) is None


def test_ensemble_rejects_material_direction_conflict():
    signal = ensemble.ensemble_signal({
        "child_signals": [
            _child("opening_range_retest", "BUY_CALL", 0.8, confidence=0.8, sha="a"),
            _child("failed_breakout_trap", "BUY_PUT", 0.78, confidence=0.8, sha="b"),
        ]
    })
    assert signal is None


def test_equity_and_futures_aliases_obey_same_contract():
    payload = {"child_signals": [_child("trend_pullback", "BUY_CALL", 0.8)]}
    assert ensemble.equity_signal(payload) is not None
    assert ensemble.futures_signal(payload) is not None
