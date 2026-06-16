from core.strategy_spec import FAMILY_MEAN_REVERSION, FAMILY_MOVEMENT, build_strategy_spec_registry


def test_registry_includes_movement_contract_entries():
    registry = build_strategy_spec_registry()

    opening = registry.get("opening_range_retest")
    pullback = registry.get("trend_pullback")
    mean_reversion = registry.get("mean_reversion_extension")

    assert opening is not None
    assert opening.family == FAMILY_MOVEMENT
    assert opening.preferred_regimes == ("OPENING_DISCOVERY", "BULL_TREND")
    assert "session_state" in opening.required_evidence_keys
    assert "structure_state" in opening.required_evidence_keys

    assert pullback is not None
    assert pullback.family == FAMILY_MOVEMENT
    assert pullback.preferred_regimes == ("BULL_TREND", "BEAR_TREND")
    assert "anchor_state" in pullback.required_evidence_keys
    assert "retracement_state" in pullback.required_evidence_keys

    assert mean_reversion is not None
    assert mean_reversion.family == FAMILY_MEAN_REVERSION
    assert mean_reversion.preferred_regimes == ("RANGE_BOUND",)
    assert "mean_reversion_anchor" in mean_reversion.required_evidence_keys
    assert "oscillator_confirmation" in mean_reversion.required_evidence_keys


def test_registry_payload_surfaces_movement_ids():
    registry = build_strategy_spec_registry()
    payload = registry.to_payload()
    strategy_ids = set(payload["strategy_ids"])

    assert "opening_range_retest" in strategy_ids
    assert "trend_pullback" in strategy_ids
    assert "mean_reversion_extension" in strategy_ids
