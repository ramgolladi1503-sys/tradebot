from dataclasses import replace

from core.strategy_parameter_profiles import (
    COMPATIBILITY_ALIAS,
    DEFAULT_PROFILES,
    EXACT_PROFILE,
    MISSING_PROFILE,
    PROFILE_VALUE_DRIFT,
    StrategyParameterProfile,
    DefaultStrategyEvidenceStore,
    build_profile_parameter_hash,
    build_profile_resolution_record,
    classify_profile_resolution,
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
    expected_hash = build_profile_parameter_hash(
        resolved_profile_id="test_v1",
        profile_version="v1",
        params={"A": 1, "B": 2},
    )
    assert profile.parameter_hash == expected_hash
    assert profile.params_hash == expected_hash

def test_get_default_profile():
    profile = get_default_profile("opening_drive_v1", "v1")
    assert profile is not None
    assert profile.strategy_id == "opening_drive"
    assert profile.strategy_version == "v1"
    assert profile.profile_version == "v1"
    assert profile.requested_profile_id == "opening_drive_v1"
    assert profile.resolved_profile_id == "opening_drive_v1"
    assert profile.resolution_source == EXACT_PROFILE
    assert "MIN_OPEN_MOVE_PCT" in profile.params
    assert profile.parameter_hash == profile.params_hash
    
def test_get_default_profile_fallback():
    profile = get_default_profile("unknown_strategy", "v1")
    assert profile is None
    assert classify_profile_resolution("unknown_strategy", "v1") == MISSING_PROFILE


def test_get_default_profile_supports_compatibility_aliases_without_value_drift():
    alias_profile = get_default_profile("opening_range_retest_v1", "v1")
    canonical_profile = get_default_profile("opening_range_breakout_v1", "v1")

    assert alias_profile is not None
    assert canonical_profile is not None
    assert alias_profile.resolution_source == COMPATIBILITY_ALIAS
    assert alias_profile.requested_profile_id == "opening_range_retest_v1"
    assert alias_profile.resolved_profile_id == "opening_range_breakout_v1"
    assert alias_profile.params == canonical_profile.params
    assert alias_profile.params_hash == canonical_profile.params_hash
    assert classify_profile_resolution("opening_range_retest_v1", "v1") == COMPATIBILITY_ALIAS
    assert build_profile_resolution_record("opening_range_retest_v1", "v1")["mismatch_classification"] == COMPATIBILITY_ALIAS


def test_exact_profile_drift_fails_closed_to_preserve_embedded_defaults(monkeypatch):
    monkeypatch.setitem(
        DEFAULT_PROFILES,
        "opening_drive_v1",
        replace(
            DEFAULT_PROFILES["opening_drive_v1"],
            params={
                "MAX_OPENING_DRIVE_MINUTES": 99,
                "MIN_OPEN_MOVE_PCT": 0.0015,
                "MIN_VWAP_ALIGNMENT_PCT": 0.0005,
            },
        ),
    )

    assert get_default_profile("opening_drive_v1", "v1") is None
    assert classify_profile_resolution("opening_drive_v1", "v1") == PROFILE_VALUE_DRIFT

def test_evidence_store_default_promotion_state():
    store = DefaultStrategyEvidenceStore()
    decision = store.get_promotion_state("unknown_strategy", "v1", "hash123", "ANY", "ANY", "ANY")
    assert decision.promotion_state == "ADVISORY_ONLY"

def test_evidence_store_can_promote():
    store = DefaultStrategyEvidenceStore()
    decision = store.get_promotion_state("opening_drive", "v1", "hash123", "ANY", "ANY", "ANY")
    # By default, without loading evidence, it's ADVISORY_ONLY
    assert decision.promotion_state == "ADVISORY_ONLY"
