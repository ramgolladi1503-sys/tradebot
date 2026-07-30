from core.hard_downgrade_engine import HardDowngradeDecision
from core.movement_regime import MovementRegimeResult
from core.opportunity_scoring import ADVISORY_ONLY, SCORE_ELIGIBLE, score_candidate
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from strategies.movement._utils import SideEvidence, make_candidate


def _market_symbol(*, regime_status: str = "VALID") -> dict:
    return {
        "ltp": 24000.0,
        "vwap": 23980.0,
        "day_high": 24050.0,
        "day_low": 23850.0,
        "ts_epoch": 1_785_000_000.0,
        "metadata": {"existing_metadata": "preserved"},
        "regime": {
            "primary_regime": "TREND",
            "scores": {"TREND_UP": 0.8, "VOLATILITY_EXPANSION": 0.2},
            "session_bucket": "MID_SESSION",
            "regime_entropy": 0.55,
            "regime_entropy_normalized": 0.34,
            "regime_entropy_state": "LOW",
            "regime_status": regime_status,
            "stable_regime": "TREND",
            "stable_regime_confirmed": True,
            "trend_state": "STRONG",
            "is_expiry_day": False,
            "volume_impulse": False,
            "model_source": "HEURISTIC_STRUCTURAL_V2_UNCALIBRATED",
            "model_hash": None,
            "probability_calibrated": False,
            "probability_semantics": "deterministic_structural_pseudo_probability",
            "regime_top_two_margin": 0.72,
            "feature_quality": {
                "status": regime_status,
                "required_coverage": 1.0,
            },
        },
        "option_chain_summary": {
            "ce_ltp": 150.0,
            "pe_ltp": 145.0,
            "ce_spread_pct": 1.0,
            "pe_spread_pct": 1.0,
            "ce_depth": 500.0,
            "pe_depth": 500.0,
            "liquidity_quality": "GOOD",
        },
        "feed_health": {
            "quote_source": "live",
            "fallback_used": False,
            "option_ltp_age_sec": 0.5,
        },
    }


def _movement_regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.8,
            "VOLATILITY_EXPANSION": 0.2,
            "TRAP_RISK": 0.0,
        },
    )


def _side() -> SideEvidence:
    return SideEvidence(
        direction="BUY_CALL",
        option_ltp=150.0,
        premium_change=10.0,
        spread_pct=1.0,
        depth=500.0,
        blockers=(),
        warnings=(),
        option_confirmation_score=0.8,
        liquidity_score=0.8,
        freshness_score=0.8,
    )


def _decision(strategy_id: str) -> HardDowngradeDecision:
    return HardDowngradeDecision(
        strategy_id=strategy_id,
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="TREND_PULLBACK",
        original_bucket="EXECUTABLE_CANDIDATE",
        downgraded_bucket="EXECUTABLE_CANDIDATE",
        downgraded=False,
        executable_candidate=True,
        downgrade_reasons=(),
        blockers=(),
        hard_blockers=(),
        warnings=(),
        safety_flags=(),
        evidence_flags=(),
    )


def _candidate(*, regime_status: str = "VALID"):
    ctx = _strategy_context_from_market_symbol(
        "NIFTY",
        _market_symbol(regime_status=regime_status),
    )
    return ctx, make_candidate(
        ctx=ctx,
        regime=_movement_regime(),
        strategy_id="trend_pullback_v1",
        movement_type="TREND_PULLBACK",
        direction="BUY_CALL",
        price_structure_score=0.8,
        side=_side(),
        entry_trigger="test",
        invalid_if="test",
        rank_reason="test",
        evidence={"strategy_specific": True},
        promotion_state="PROMOTED",
    )


def test_market_snapshot_regime_truth_reaches_candidate_evidence():
    ctx, candidate = _candidate()
    policy_context = ctx.metadata["regime_policy_context"]
    assert ctx.metadata["existing_metadata"] == "preserved"
    assert policy_context["session_bucket"] == "MID_SESSION"
    assert policy_context["regime_status"] == "VALID"
    assert policy_context["model_source"] == "HEURISTIC_STRUCTURAL_V2_UNCALIBRATED"
    assert candidate.evidence["strategy_specific"] is True
    assert candidate.evidence["entropy_state"] == {
        "current_value": 0.55,
        "normalized": 0.34,
        "state": "LOW",
    }
    assert candidate.evidence["stable_regime_confirmed"] is True
    assert candidate.evidence["probability_calibrated"] is False


def test_string_false_values_do_not_become_true_policy_flags():
    data = _market_symbol()
    data["regime"]["stable_regime_confirmed"] = "false"
    data["regime"]["probability_calibrated"] = "false"
    data["regime"]["is_expiry_day"] = "false"
    data["regime"]["volume_impulse"] = "false"
    data["expiry_context"] = {"is_expiry": True}
    ctx = _strategy_context_from_market_symbol("NIFTY", data)
    policy_context = ctx.metadata["regime_policy_context"]
    assert policy_context["stable_regime_confirmed"] is False
    assert policy_context["probability_calibrated"] is False
    assert policy_context["is_expiry_day"] is False
    assert policy_context["volume_impulse"] is False


def test_valid_propagated_regime_truth_can_remain_score_eligible():
    _, candidate = _candidate(regime_status="VALID")
    result = score_candidate(candidate, _decision(candidate.strategy_id))
    assert result.score_eligibility == SCORE_ELIGIBLE
    assert result.executable_candidate is True


def test_invalid_propagated_regime_truth_forces_advisory():
    _, candidate = _candidate(regime_status="INVALID_INPUT")
    result = score_candidate(candidate, _decision(candidate.strategy_id))
    assert result.score_eligibility == ADVISORY_ONLY
    assert result.bucket == "ADVISORY_CANDIDATE"
    assert result.executable_candidate is False
