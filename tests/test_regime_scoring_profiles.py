from core.movement_regime import MovementRegimeResult
from core.regime_scoring_profiles import resolve_regime_scoring_profile


def _regime(primary="TREND_UP", **scores):
    base = {
        "TREND_UP": 0.0,
        "TREND_DOWN": 0.0,
        "RANGE": 0.0,
        "CHOP": 0.0,
        "COMPRESSION": 0.0,
        "VOLATILITY_EXPANSION": 0.0,
        "TRAP_RISK": 0.0,
        "EXHAUSTION_RISK": 0.0,
        "EXPIRY_CONTEXT": 0.0,
        "INCONCLUSIVE": 0.0,
    }
    base.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime=primary, scores=base)


def test_trend_profile_is_read_only_and_normalized():
    profile = resolve_regime_scoring_profile(_regime("TREND_UP", TREND_UP=0.9))

    assert profile.read_only is True
    assert profile.is_order_action is False
    assert profile.append is False
    assert profile.primary_regime == "TREND_UP"
    assert profile.selected_profiles == ("TREND_UP",)
    assert abs(sum(profile.adjusted_component_weights.values()) - 1.0) < 0.00001
    assert profile.adjusted_component_weights["regime_alignment"] > profile.base_component_weights["regime_alignment"]
    assert profile.adjusted_component_weights["price_structure"] > profile.base_component_weights["price_structure"]
    assert profile.metadata["scope"] == "read_only_no_execution_no_ranking"


def test_chop_profile_recommends_safety_cap_and_warnings():
    profile = resolve_regime_scoring_profile(_regime("CHOP", CHOP=0.85))

    assert profile.primary_regime == "CHOP"
    assert profile.recommended_score_cap == 0.2
    assert profile.recommended_penalties["chop_regime_penalty"] == 0.35
    assert "profile_chop_should_not_promote_directional_candidates" in profile.warnings
    assert profile.adjusted_component_weights["liquidity"] > profile.base_component_weights["liquidity"]
    assert profile.adjusted_component_weights["freshness"] > profile.base_component_weights["freshness"]


def test_compression_profile_increases_timing_and_volatility_weights():
    profile = resolve_regime_scoring_profile(_regime("COMPRESSION", COMPRESSION=0.8))

    assert profile.adjusted_component_weights["timing"] > profile.base_component_weights["timing"]
    assert profile.adjusted_component_weights["volatility"] > profile.base_component_weights["volatility"]
    assert any("compression_profile" in item for item in profile.rationale)


def test_volatility_expansion_profile_prioritizes_volatility_freshness_and_liquidity():
    profile = resolve_regime_scoring_profile(_regime("VOLATILITY_EXPANSION", VOLATILITY_EXPANSION=0.9))

    assert profile.adjusted_component_weights["volatility"] > profile.base_component_weights["volatility"]
    assert profile.adjusted_component_weights["freshness"] > profile.base_component_weights["freshness"]
    assert profile.adjusted_component_weights["liquidity"] > profile.base_component_weights["liquidity"]


def test_trap_risk_profile_recommends_cap_penalty_and_confirmation_bias():
    profile = resolve_regime_scoring_profile(_regime("TRAP_RISK", TRAP_RISK=0.9))

    assert profile.recommended_score_cap == 0.45
    assert profile.recommended_penalties["trap_risk_regime_penalty"] == 0.25
    assert profile.adjusted_component_weights["option_confirmation"] > profile.base_component_weights["option_confirmation"]
    assert profile.adjusted_component_weights["price_structure"] < profile.base_component_weights["price_structure"]
    assert "profile_trap_risk_requires_extra_confirmation" in profile.warnings


def test_expiry_profile_biases_liquidity_freshness_and_option_confirmation():
    profile = resolve_regime_scoring_profile(_regime("EXPIRY_CONTEXT", EXPIRY_CONTEXT=0.9))

    assert profile.recommended_score_cap == 0.75
    assert profile.adjusted_component_weights["liquidity"] > profile.base_component_weights["liquidity"]
    assert profile.adjusted_component_weights["freshness"] > profile.base_component_weights["freshness"]
    assert profile.adjusted_component_weights["option_confirmation"] > profile.base_component_weights["option_confirmation"]


def test_inconclusive_profile_recommends_advisory_bias():
    profile = resolve_regime_scoring_profile(_regime("INCONCLUSIVE", INCONCLUSIVE=1.0))

    assert profile.recommended_score_cap == 0.35
    assert profile.recommended_penalties["inconclusive_regime_penalty"] == 0.25
    assert "profile_inconclusive_regime_requires_advisory_bias" in profile.warnings
    assert profile.adjusted_component_weights["liquidity"] > profile.base_component_weights["liquidity"]


def test_secondary_regime_profiles_are_selected_when_above_threshold():
    profile = resolve_regime_scoring_profile(
        _regime("TREND_UP", TREND_UP=0.8, TRAP_RISK=0.7, EXPIRY_CONTEXT=0.6)
    )

    assert profile.selected_profiles == ("TREND_UP", "TRAP_RISK", "EXPIRY_CONTEXT")
    assert profile.recommended_score_cap == 0.45
    assert set(profile.recommended_penalties) >= {"trap_risk_regime_penalty", "expiry_context_risk_penalty"}
    assert "profile_trap_risk_requires_extra_confirmation" in profile.warnings


def test_secondary_threshold_can_be_overridden():
    profile = resolve_regime_scoring_profile(
        _regime("TREND_UP", TREND_UP=0.8, RANGE=0.5),
        secondary_threshold=0.45,
    )

    assert profile.selected_profiles == ("TREND_UP", "RANGE")


def test_profile_accepts_mapping_payload():
    regime = _regime("RANGE", RANGE=0.8).to_dict()

    profile = resolve_regime_scoring_profile(regime)

    assert profile.primary_regime == "RANGE"
    assert profile.selected_profiles == ("RANGE",)


def test_profile_rejects_zero_sum_custom_weights():
    try:
        resolve_regime_scoring_profile(_regime("TREND_UP"), base_component_weights={"price_structure": 0.0})
    except ValueError as exc:
        assert "regime_scoring_profile_weights_sum_zero" in str(exc)
    else:
        raise AssertionError("profile resolver accepted zero-sum weights")


def test_profile_is_json_serializable():
    profile = resolve_regime_scoring_profile(_regime("TREND_UP", TREND_UP=0.9))
    payload = profile.to_json()

    assert "regime_scoring_profile_v1" in payload
    assert "adjusted_component_weights" in payload
