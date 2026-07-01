import pytest
import json
from core.strategy_parameter_profiles import (
    StrategyParameterProfile,
    StrategyEvidenceDecision,
    DefaultStrategyEvidenceStore,
    DEFAULT_PROFILES,
    get_default_profile,
)

def test_strategy_parameter_profile_hash_is_deterministic():
    profile = StrategyParameterProfile(
        strategy_id="test_v1",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={"B": 2, "A": 1}
    )
    profile2 = StrategyParameterProfile(
        strategy_id="test_v1",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={"A": 1, "B": 2}
    )
    assert profile.params_hash == profile2.params_hash
    # The hash should be a sha256 hex string of the sorted json params context
    context_dict = {
        "strategy_id": "test_v1",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {"A": 1, "B": 2},
    }
    expected_json = json.dumps(context_dict, sort_keys=True)
    import hashlib
    expected_hash = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()
    assert profile.params_hash == expected_hash

def test_get_default_profile():
    profile = get_default_profile("opening_drive_v1", "v1")
    assert profile is not None
    assert profile.strategy_id == "opening_drive"
    assert profile.strategy_version == "v1"
    assert "MIN_OPEN_MOVE_PCT" in profile.params
    
def test_get_default_profile_fallback():
    profile = get_default_profile("unknown_strategy", "v1")
    assert profile is None

def test_evidence_store_default_promotion_state():
    store = DefaultStrategyEvidenceStore()
    decision = store.get_promotion_state("unknown_strategy", "v1", "hash123", "ANY", "ANY", "ANY")
    assert decision.promotion_state == "ADVISORY_ONLY"

def test_evidence_store_can_promote():
    store = DefaultStrategyEvidenceStore()
    decision = store.get_promotion_state("opening_drive", "v1", "hash123", "ANY", "ANY", "ANY")
    # By default, without loading evidence, it's ADVISORY_ONLY
    assert decision.promotion_state == "ADVISORY_ONLY"
