from strategies.ensemble import ensemble_signal


def _child(strategy_id, direction, score=0.8, confidence=0.8, sha="abc"):
    return {
        "direction":direction,
        "score":score,
        "confidence":confidence,
        "reason":"unit",
        "source_strategy_id":strategy_id,
        "source_sha256":sha,
        "structural_status":"STRUCTURALLY_VALID",
        "evidence":{"contract_valid":True,"freshness_valid":True},
    }


def test_ensemble_aggregates_only_structurally_valid_child_signals():
    sig=ensemble_signal({"child_signals":[_child("trend_pullback","BUY_CALL"),_child("opening_range_retest","BUY_CALL",sha="def")]})
    assert sig is not None and sig.direction=="BUY_CALL"
    assert sig.structural_status=="STRUCTURALLY_VALID"
    assert set(sig.evidence["child_strategy_ids"])=={"trend_pullback","opening_range_retest"}


def test_ensemble_fails_closed_without_child_provenance():
    assert ensemble_signal({"ltp":102,"vwap":100,"regime":"TREND"}) is None
    bad=_child("trend_pullback","BUY_CALL"); bad["source_sha256"]=""
    assert ensemble_signal({"child_signals":[bad]}) is None


def test_ensemble_rejects_material_direction_conflict():
    assert ensemble_signal({"child_signals":[_child("a","BUY_CALL",0.8,0.8),_child("b","BUY_PUT",0.8,0.8,sha="def")]}) is None
