from core.candidate_classifier import classify_candidates
from core.hard_downgrade_engine import apply_hard_downgrades
from core.movement_contract import StrategyCandidate
from core.opportunity_scoring import SCORE_ELIGIBLE, SUPPRESSED_BY_DOWNGRADE
from core.profile_score_delta_evidence import build_profile_score_delta_evidence


PROFILE_WEIGHTS = {
    "confluence": 0.04,
    "freshness": 0.10,
    "liquidity": 0.10,
    "option_confirmation": 0.10,
    "price_structure": 0.08,
    "regime_alignment": 0.38,
    "timing": 0.10,
    "volatility": 0.10,
}


def _candidate(strategy_id, *, regime_alignment_score, price_structure_score=0.4, blockers=(), warnings=()):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type="COMPRESSION_BREAKOUT",
        symbol="NIFTY",
        direction="BUY_CALL",
        status="VALIDATED_CANDIDATE",
        raw_score=0.75,
        confidence_score=0.75,
        price_structure_score=price_structure_score,
        option_confirmation_score=0.55,
        liquidity_score=0.55,
        freshness_score=0.55,
        volatility_score=0.55,
        regime_alignment_score=regime_alignment_score,
        timing_score=0.55,
        trap_risk_score=0.0,
        confluence_score=0.55,
        entry_trigger="unit",
        invalid_if="unit",
        rank_reason="unit",
        blockers=blockers,
        warnings=warnings,
    )


def _downgrade_report(candidates):
    return apply_hard_downgrades(classify_candidates(candidates))


def test_profile_delta_report_explains_score_and_shadow_rank_stability():
    weak_regime = _candidate("weak_regime", regime_alignment_score=0.10, price_structure_score=1.0)
    strong_regime = _candidate("strong_regime", regime_alignment_score=1.0, price_structure_score=0.4)
    candidates = [weak_regime, strong_regime]

    report = build_profile_score_delta_evidence(candidates, _downgrade_report(candidates), scoring_profile=PROFILE_WEIGHTS)

    payload = report.to_dict()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert report.metadata["scope"] == "offline_profile_score_delta_evidence_only"
    assert report.metadata["rank_estimate_source"] == "candidate_ranking_v1_shadow_reports"
    assert report.metadata["profile_sort_cutover_enabled"] is False
    assert report.metadata["runtime_wiring_changed"] is False

    by_id = {record.candidate_id: record for record in report.records}
    assert by_id["strong_regime"].score_delta > 0
    assert by_id["weak_regime"].score_delta < 0
    assert by_id["strong_regime"].rank_delta == 0
    assert by_id["weak_regime"].rank_delta == 0
    assert "SCORE_UP_RANK_UNCHANGED" in by_id["strong_regime"].promotion_or_demotion_reason
    assert "regime_alignment" in by_id["strong_regime"].promotion_or_demotion_reason
    assert "SCORE_DOWN_RANK_UNCHANGED" in by_id["weak_regime"].promotion_or_demotion_reason
    assert report.promoted_count == 0
    assert report.demoted_count == 0
    assert report.unchanged_rank_count == 2
    assert report.safety_status_changed_count == 0


def test_profile_delta_preserves_safety_status_for_suppressed_candidate():
    risky = _candidate(
        "risky_high_regime",
        regime_alignment_score=1.0,
        price_structure_score=1.0,
        blockers=("FALLBACK_QUOTE_ONLY",),
    )
    clean = _candidate("clean", regime_alignment_score=0.7)
    candidates = [risky, clean]

    report = build_profile_score_delta_evidence(candidates, _downgrade_report(candidates), scoring_profile=PROFILE_WEIGHTS)
    risky_record = {record.candidate_id: record for record in report.records}["risky_high_regime"]

    assert risky_record.safety_status_unchanged is True
    assert risky_record.default_score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert risky_record.profile_score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert risky_record.default_executable_candidate is False
    assert risky_record.profile_executable_candidate is False
    assert "FALLBACK_QUOTE_ONLY" in risky_record.blockers
    assert report.safety_status_changed_count == 0


def test_profile_delta_requires_explicit_profile():
    candidate = _candidate("candidate", regime_alignment_score=0.5)

    try:
        build_profile_score_delta_evidence([candidate], _downgrade_report([candidate]), scoring_profile=None)
    except ValueError as exc:
        assert "profile_score_delta_requires_scoring_profile" in str(exc)
    else:
        raise AssertionError("score delta evidence accepted absent profile")


def test_profile_delta_records_component_breakdown_for_each_candidate():
    candidate = _candidate("candidate", regime_alignment_score=1.0)
    report = build_profile_score_delta_evidence([candidate], _downgrade_report([candidate]), scoring_profile=PROFILE_WEIGHTS)

    record = report.records[0]
    by_component = {delta.component: delta for delta in record.component_delta_breakdown}

    assert set(by_component) == set(PROFILE_WEIGHTS)
    assert by_component["regime_alignment"].profile_weight == PROFILE_WEIGHTS["regime_alignment"]
    assert by_component["regime_alignment"].weighted_delta > 0
    assert record.default_score_eligibility == SCORE_ELIGIBLE
    assert record.profile_score_eligibility == SCORE_ELIGIBLE
