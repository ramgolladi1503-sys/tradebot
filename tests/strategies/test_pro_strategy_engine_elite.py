from strategies.pro_layer.pro_strategy_engine import ProStrategyEngine


def _child(name, family, direction="BUY_CALL", score=0.8, confidence=0.8, **evidence_overrides):
    evidence = {
        "structural_status": "STRUCTURALLY_VALID",
        "contract_valid": True,
        "freshness_valid": True,
        "source_sha256": f"sha-{name}",
    }
    evidence.update(evidence_overrides)
    return {
        "name": name,
        "family": family,
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "reason": "child",
        "regime_tags": ["TREND"],
        "evidence": evidence,
    }


def test_invalid_child_fails_complete_meta_decision_closed():
    engine = ProStrategyEngine()
    errors: list[str] = []
    signals = engine.run(
        {"pro_child_signals": [_child("a", "trend"), _child("b", "flow", freshness_valid=False)]},
        error_sink=errors,
    )
    assert signals == []
    assert errors == ["invalid_pro_child_signal:1"]


def test_missing_child_input_never_synthesizes_alpha():
    engine = ProStrategyEngine()
    assert engine.run({"regime": "TREND", "ltp": 102, "vwap": 100, "atr": 2.0}) == []


def test_single_family_cannot_create_meta_signal():
    engine = ProStrategyEngine()
    assert engine.run({"pro_child_signals": [_child("a", "trend"), _child("b", "trend")]}) == []


def test_conflicting_family_consensus_fails_closed():
    engine = ProStrategyEngine()
    signals = engine.run(
        {
            "pro_child_signals": [
                _child("a", "trend", "BUY_CALL", 0.8, 0.8),
                _child("b", "flow", "BUY_PUT", 0.78, 0.8),
            ]
        }
    )
    assert signals == []


def test_two_structurally_valid_families_can_form_one_consensus():
    engine = ProStrategyEngine()
    signals = engine.run(
        {
            "pro_child_signals": [
                _child("a", "trend", "BUY_CALL", 0.82, 0.80),
                _child("b", "flow", "BUY_CALL", 0.76, 0.75),
            ]
        }
    )
    assert len(signals) == 1
    signal = signals[0]
    assert signal.name == "pro_strategy_consensus"
    assert signal.direction == "BUY_CALL"
    assert signal.evidence["structural_status"] == "STRUCTURALLY_VALID"
    assert signal.evidence["contract_valid"] is True
    assert signal.evidence["freshness_valid"] is True
    assert signal.evidence["family_truth"] == ("flow", "trend")
