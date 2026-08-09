from strategies.pro_layer.pro_strategy_engine import ProStrategyEngine, ProSignal, ProSignalAggregator


def _child(name, family, direction="BUY_CALL", score=0.8, confidence=0.8, **evidence_overrides):
    evidence = {
        "structural_status": "STRUCTURALLY_VALID",
        "contract_valid": True,
        "freshness_valid": True,
        "source_sha256": f"sha-{name}",
    }
    evidence.update(evidence_overrides)
    return ProSignal(
        name=name,
        direction=direction,
        score=score,
        confidence=confidence,
        reason="child",
        family=family,
        regime_tags=["TREND"],
        evidence=evidence,
    )


def test_pro_engine_does_not_generate_hidden_alpha_without_children():
    engine = ProStrategyEngine()
    assert engine.run({
        "regime": "TREND",
        "ltp": 102.0,
        "vwap": 100.0,
        "atr": 2.0,
        "bid_qty": 2000,
        "ask_qty": 500,
        "call_oi_delta": 500,
        "put_oi_delta": 2000,
    }) == []


def test_pro_engine_rejects_missing_structural_provenance():
    engine = ProStrategyEngine()
    bad = _child("a", "trend", structural_status="UNKNOWN")
    errors: list[str] = []
    assert engine.run({"pro_child_signals": [bad]}, error_sink=errors) == []
    assert errors == ["invalid_pro_child_signal:0"]


def test_pro_engine_rejects_missing_source_hash():
    engine = ProStrategyEngine()
    bad = _child("a", "trend", source_sha256="")
    assert engine.run({"pro_child_signals": [bad]}) == []


def test_pro_engine_rejects_stale_child():
    engine = ProStrategyEngine()
    bad = _child("a", "trend", freshness_valid=False)
    assert engine.run({"pro_child_signals": [bad]}) == []


def test_pro_engine_requires_orthogonal_family_diversity():
    engine = ProStrategyEngine()
    assert engine.run({"pro_child_signals": [_child("a", "trend"), _child("b", "trend")]}) == []


def test_pro_engine_rejects_material_direction_conflict():
    engine = ProStrategyEngine()
    result = engine.run({
        "pro_child_signals": [
            _child("a", "trend", "BUY_CALL", 0.8, 0.8),
            _child("b", "flow", "BUY_PUT", 0.8, 0.8),
        ]
    })
    assert result == []


def test_pro_engine_emits_consensus_only_from_two_valid_families():
    engine = ProStrategyEngine()
    result = engine.run({
        "pro_child_signals": [
            _child("a", "trend", "BUY_CALL", 0.82, 0.80),
            _child("b", "flow", "BUY_CALL", 0.76, 0.75),
        ]
    })
    assert len(result) == 1
    signal = result[0]
    assert signal.name == "pro_strategy_consensus"
    assert signal.direction == "BUY_CALL"
    assert signal.family == "pro_meta"
    assert signal.evidence["family_truth"] == ("flow", "trend")
    assert signal.evidence["source_sha256"] == "sha-a|sha-b"


def test_aggregator_rejects_weak_top_signal():
    agg = ProSignalAggregator()
    result = agg.aggregate([
        _child("a", "trend", score=0.60, confidence=0.59),
        _child("b", "flow", score=0.60, confidence=0.59),
    ])
    assert result == []
