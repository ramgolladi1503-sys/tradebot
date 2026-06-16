from core.strategy_spec import (
    FAMILY_PAIR_ARBITRAGE,
    FAMILY_VWAP_ORB,
    build_strategy_spec_registry,
)


def test_registry_includes_vwap_orb_and_pairs_arbitrage_families():
    registry = build_strategy_spec_registry()

    vwap_orb = registry.get("vwap_orb")
    pairs = registry.get("pairs_arbitrage")

    assert vwap_orb is not None
    assert vwap_orb.family == FAMILY_VWAP_ORB
    assert vwap_orb.preferred_regimes == ("OPENING_DISCOVERY", "BULL_TREND")
    assert "vwap_state" in vwap_orb.required_evidence_keys
    assert "quote_truth" in vwap_orb.required_evidence_keys

    assert pairs is not None
    assert pairs.family == FAMILY_PAIR_ARBITRAGE
    assert pairs.preferred_regimes == ("RANGE_BOUND",)
    assert pairs.direction_capabilities == ("LONG_SPREAD", "SHORT_SPREAD")
    assert "cross_asset_health" in pairs.required_evidence_keys
    assert "leg_freshness_a" in pairs.required_evidence_keys
    assert "leg_freshness_b" in pairs.required_evidence_keys


def test_registry_payload_surfaces_new_family_ids():
    registry = build_strategy_spec_registry()
    payload = registry.to_payload()
    strategy_ids = set(payload["strategy_ids"])

    assert "vwap_orb" in strategy_ids
    assert "pairs_arbitrage" in strategy_ids
