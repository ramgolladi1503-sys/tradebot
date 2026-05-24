from __future__ import annotations

import json

from core.exact_option_token_freshness_gate import (
    EXACT_OPTION_TOKEN_FRESHNESS_BLOCKER,
    TOKEN_IDENTITY_MISSING_REASON,
    TOKEN_MISMATCH_REASON,
    TOKEN_MISSING_REASON,
    TOKEN_TICK_AGE_MISSING_REASON,
    TOKEN_TICK_STALE_REASON,
    apply_exact_option_token_freshness_to_ranking,
    classify_exact_option_token_freshness,
)
from core.opportunity_scoring import SCORE_ELIGIBLE, OpportunityScoreBreakdown, OpportunityScoreRecord, OpportunityScoreReport

# exact token safety regression coverage: stale/mismatched option token evidence cannot produce executable rankings.


def _breakdown(final_score: float = 0.7) -> OpportunityScoreBreakdown:
    return OpportunityScoreBreakdown(
        component_scores={},
        component_weights={},
        weighted_component_scores={},
        base_score=final_score,
        penalties={},
        total_penalty=0.0,
        bucket_cap=1.0,
        trap_risk_penalty=0.0,
        final_score=final_score,
    )


def _score(strategy_id: str = "s1", final_score: float = 0.7) -> OpportunityScoreRecord:
    return OpportunityScoreRecord(
        strategy_id=strategy_id,
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="COMPRESSION_BREAKOUT",
        bucket="EXECUTABLE_CANDIDATE",
        score_eligibility=SCORE_ELIGIBLE,
        final_score=final_score,
        executable_candidate=True,
        score_explanation="unit",
        downgrade_reasons=(),
        safety_flags=(),
        blockers=(),
        warnings=(),
        breakdown=_breakdown(final_score),
    )


def _report(scores: list[OpportunityScoreRecord]) -> OpportunityScoreReport:
    return OpportunityScoreReport(
        schema_version=1,
        read_only=True,
        is_order_action=False,
        append=False,
        score_count=len(scores),
        score_eligible_count=len(scores),
        needs_confirmation_count=0,
        advisory_count=0,
        suppressed_count=0,
        no_trade_count=0,
        scores=tuple(scores),
        blockers=(),
        warnings=(),
        safety_flags=(),
        metadata={"scorer": "opportunity_score_v1"},
    )


def _fresh_token():
    return {
        "symbol": "NIFTY",
        "expected_token": "12345",
        "observed_token": "12345",
        "tick_age_sec": 0.4,
        "expiry": "2026-05-28",
        "strike": 23000,
        "option_type": "CE",
    }


def test_exact_option_token_freshness_decision_is_read_only_and_non_action():
    decision = classify_exact_option_token_freshness(_fresh_token(), max_tick_age_sec=3.0)

    assert decision.read_only is True
    assert decision.is_order_action is False
    assert decision.append is False
    assert decision.gate_active is False
    assert decision.token_freshness_ok is True
    assert decision.blockers == ()
    assert decision.records[0].token_ok is True
    assert decision.records[0].fresh is True


def test_exact_option_token_mismatch_suppresses_all_executable_ranks():
    score_report = _report([_score("a", 0.9), _score("b", 0.8)])
    token_evidence = dict(_fresh_token(), observed_token="99999")

    ranking = apply_exact_option_token_freshness_to_ranking(score_report, token_evidence, max_tick_age_sec=3.0)

    assert ranking.read_only is True
    assert ranking.is_order_action is False
    assert ranking.append is False
    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert ranking.ranks == ()
    assert ranking.safety_flags == (EXACT_OPTION_TOKEN_FRESHNESS_BLOCKER,)
    assert f"NIFTY:{TOKEN_MISMATCH_REASON}" in ranking.blockers
    assert ranking.metadata["exact_option_token_freshness_active"] is True
    assert ranking.metadata["source_score_count"] == 2


def test_exact_option_token_stale_tick_suppresses_all_executable_ranks():
    score_report = _report([_score("candidate", 0.9)])
    token_evidence = dict(_fresh_token(), tick_age_sec=5.1)

    ranking = apply_exact_option_token_freshness_to_ranking(score_report, token_evidence, max_tick_age_sec=3.0)

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert f"NIFTY:{TOKEN_TICK_STALE_REASON}" in ranking.blockers


def test_exact_option_token_missing_tick_age_fails_closed():
    score_report = _report([_score("candidate", 0.9)])
    token_evidence = dict(_fresh_token(), tick_age_sec=None)

    ranking = apply_exact_option_token_freshness_to_ranking(score_report, token_evidence, max_tick_age_sec=3.0)

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert f"NIFTY:{TOKEN_TICK_AGE_MISSING_REASON}" in ranking.blockers


def test_exact_option_token_missing_token_fails_closed():
    score_report = _report([_score("candidate", 0.9)])
    token_evidence = dict(_fresh_token(), observed_token="")

    ranking = apply_exact_option_token_freshness_to_ranking(score_report, token_evidence, max_tick_age_sec=3.0)

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert f"NIFTY:{TOKEN_MISSING_REASON}" in ranking.blockers


def test_exact_option_token_missing_identity_fails_closed():
    score_report = _report([_score("candidate", 0.9)])

    ranking = apply_exact_option_token_freshness_to_ranking(score_report, None, max_tick_age_sec=3.0)

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert EXACT_OPTION_TOKEN_FRESHNESS_BLOCKER in ranking.blockers
    assert TOKEN_IDENTITY_MISSING_REASON in ranking.blockers


def test_exact_option_token_fresh_evidence_preserves_normal_ranking_order():
    score_report = _report([_score("low", 0.5), _score("high", 0.9)])

    ranking = apply_exact_option_token_freshness_to_ranking(score_report, _fresh_token(), max_tick_age_sec=3.0)

    assert ranking.rank_count == 2
    assert ranking.executable_count == 2
    assert [rank.strategy_id for rank in ranking.ranks] == ["high", "low"]
    assert EXACT_OPTION_TOKEN_FRESHNESS_BLOCKER not in ranking.blockers


def test_exact_option_token_multiple_records_fail_if_any_record_is_unsafe():
    score_report = _report([_score("candidate", 0.9)])
    unsafe = dict(_fresh_token(), symbol="BANKNIFTY", expected_token="abc", observed_token="xyz")

    ranking = apply_exact_option_token_freshness_to_ranking(
        score_report,
        [_fresh_token(), unsafe],
        max_tick_age_sec=3.0,
    )

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert f"BANKNIFTY:{TOKEN_MISMATCH_REASON}" in ranking.blockers


def test_exact_option_token_report_is_json_serializable():
    decision = classify_exact_option_token_freshness(dict(_fresh_token(), observed_token="99999"), max_tick_age_sec=3.0)
    payload = json.loads(decision.to_json())

    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["gate_active"] is True
    assert payload["metadata"]["gate"] == "exact_option_token_freshness_gate_v1"
