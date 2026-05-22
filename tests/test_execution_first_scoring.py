from core.execution_first_scoring import apply_execution_first_score
from core.trade_scoring import compute_final_score


def test_execution_first_scoring_allows_strong_execution_candidate():
    decision = apply_execution_first_score(
        priority_score=0.82,
        signal_score=0.86,
        execution_score=0.78,
        candidate_class="EXECUTABLE",
        execution_ok=True,
        data_confidence=0.90,
    )

    assert decision.adjusted_score == 0.82
    assert decision.reasons == ()
    assert decision.context["applied"] is False


def test_execution_first_scoring_caps_high_signal_with_bad_execution():
    decision = apply_execution_first_score(
        priority_score=0.84,
        signal_score=0.90,
        execution_score=0.20,
        candidate_class="EXECUTABLE",
        execution_ok=True,
        data_confidence=0.90,
    )

    assert decision.adjusted_score <= 0.49
    assert decision.cap_applied == 0.49
    assert "execution_hard_floor_cap" in decision.reasons
    assert "high_signal_overridden_by_execution" in decision.reasons


def test_execution_first_scoring_caps_when_execution_not_ok():
    decision = apply_execution_first_score(
        priority_score=0.80,
        signal_score=0.88,
        execution_score=0.70,
        candidate_class="EXECUTABLE",
        execution_ok=False,
        data_confidence=0.90,
    )

    assert decision.adjusted_score <= 0.45
    assert decision.cap_applied == 0.45
    assert decision.reasons == ("execution_not_ok_cap",)


def test_execution_first_scoring_penalizes_stale_liquidity_spread_and_low_confidence():
    decision = apply_execution_first_score(
        priority_score=0.80,
        signal_score=0.82,
        execution_score=0.60,
        candidate_class="EXECUTABLE",
        execution_ok=True,
        stale_quote=True,
        missing_liquidity=True,
        spread_uncertain=True,
        data_confidence=0.20,
    )

    assert decision.adjusted_score < 0.80
    assert decision.penalty_applied > 0.0
    assert set(decision.reasons) == {
        "stale_quote_execution_penalty",
        "missing_liquidity_execution_penalty",
        "spread_uncertain_execution_penalty",
        "low_data_confidence_execution_penalty",
    }


def test_execution_first_scoring_does_not_reweight_non_executable_classes():
    decision = apply_execution_first_score(
        priority_score=0.70,
        signal_score=0.90,
        execution_score=0.10,
        candidate_class="ADVISORY_ONLY",
        execution_ok=False,
        stale_quote=True,
        missing_liquidity=True,
        spread_uncertain=True,
        data_confidence=0.10,
    )

    assert decision.adjusted_score == 0.70
    assert decision.reasons == ()
    assert decision.context["applied"] is False


def test_compute_final_score_import_uses_execution_first_wrapper():
    result = compute_final_score(
        {
            "trade_id": "EDGE34-WRAP",
            "execution_ok": True,
            "setup_score": 0.95,
            "trigger_score": 0.95,
            "entry_quality_score": 0.10,
        },
        candidate_class="EXECUTABLE",
        market_mode="LIVE",
        setup_quality=0.95,
        confluence_score=0.95,
        regime_fit=0.90,
        liquidity_quality=0.05,
        freshness_quality=0.05,
        execution_feasibility=0.05,
        data_confidence=0.90,
    )

    assert result["execution_first_applied"] is True
    assert result["final_score"] <= 0.49
    assert "execution_hard_floor_cap" in result["execution_first_reasons"]
