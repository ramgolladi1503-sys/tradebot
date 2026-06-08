import pytest

from core.candidate_classifier import classify_candidates
from core.hard_downgrade_engine import apply_hard_downgrades
from core.movement_contract import StrategyCandidate
from core.movement_regime import MovementRegimeResult
from core.opportunity_scoring import COMPONENT_WEIGHTS, score_opportunities
from core.regime_scoring_profiles import resolve_regime_scoring_profile


def _candidate(**overrides):
    payload = {
        "schema_version": 1,
        "strategy_id": "profile_candidate",
        "movement_type": "COMPRESSION_BREAKOUT",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "status": "VALIDATED_CANDIDATE",
        "raw_score": 0.75,
        "confidence_score": 0.75,
        "price_structure_score": 1.0,
        "option_confirmation_score": 0.2,
        "liquidity_score": 0.2,
        "freshness_score": 0.2,
        "volatility_score": 0.2,
        "regime_alignment_score": 1.0,
        "timing_score": 0.2,
        "trap_risk_score": 0.0,
        "confluence_score": 0.2,
        "entry_trigger": "unit",
        "invalid_if": "unit",
        "rank_reason": "unit",
        "blockers": (),
        "warnings": (),
    }
    payload.update(overrides)
    return StrategyCandidate(**payload)


def _downgrade_report(candidate):
    return apply_hard_downgrades(classify_candidates([candidate]))


def _trend_profile():
    return resolve_regime_scoring_profile(
        MovementRegimeResult(
            schema_version=1,
            primary_regime="TREND_UP",
            scores={
                "TREND_UP": 0.9,
                "TREND_DOWN": 0.0,
                "RANGE": 0.0,
                "CHOP": 0.0,
                "COMPRESSION": 0.0,
                "VOLATILITY_EXPANSION": 0.0,
                "TRAP_RISK": 0.0,
                "EXHAUSTION_RISK": 0.0,
                "EXPIRY_CONTEXT": 0.0,
                "INCONCLUSIVE": 0.0,
            },
        )
    )


def test_score_opportunities_default_path_keeps_fixed_component_weights():
    candidate = _candidate()
    report = score_opportunities([candidate], _downgrade_report(candidate))

    record = report.scores[0]
    assert record.breakdown.component_weights == COMPONENT_WEIGHTS
    assert report.metadata["component_weights"] == COMPONENT_WEIGHTS
    assert report.metadata["base_component_weights"] == COMPONENT_WEIGHTS
    assert report.metadata["scoring_profile_applied"] is False
    assert report.metadata["scoring_profile_name"] is None


def test_score_opportunities_can_opt_into_regime_profile_weights():
    candidate = _candidate()
    profile = _trend_profile()
    report = score_opportunities([candidate], _downgrade_report(candidate), scoring_profile=profile)

    record = report.scores[0]
    assert record.breakdown.component_weights == profile.adjusted_component_weights
    assert report.metadata["component_weights"] == profile.adjusted_component_weights
    assert report.metadata["base_component_weights"] == COMPONENT_WEIGHTS
    assert report.metadata["scoring_profile_applied"] is True
    assert report.metadata["scoring_profile_name"] == "TREND_UP"
    assert record.final_score != pytest.approx(
        score_opportunities([candidate], _downgrade_report(candidate)).scores[0].final_score
    )


def test_score_opportunities_accepts_explicit_component_weight_mapping():
    candidate = _candidate()
    custom_weights = {key: 0.0 for key in COMPONENT_WEIGHTS}
    custom_weights["price_structure"] = 1.0
    report = score_opportunities([candidate], _downgrade_report(candidate), scoring_profile=custom_weights)

    record = report.scores[0]
    assert record.breakdown.component_weights["price_structure"] == 1.0
    assert record.breakdown.base_score == 1.0
    assert report.metadata["scoring_profile_name"] == "custom_component_weights"


def test_score_opportunities_rejects_invalid_profile_component_shape():
    candidate = _candidate()

    with pytest.raises(ValueError, match="opportunity_scoring_profile_component_mismatch"):
        score_opportunities([candidate], _downgrade_report(candidate), scoring_profile={"price_structure": 1.0})


def test_score_report_serializes_non_action_safety_flags():
    candidate = _candidate()
    payload = score_opportunities([candidate], _downgrade_report(candidate)).to_dict()

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
