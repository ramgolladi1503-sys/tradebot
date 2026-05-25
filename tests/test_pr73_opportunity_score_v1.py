from __future__ import annotations

import json

from core.candidate_hard_downgrade import apply_candidate_hard_downgrades
from core.candidate_readiness_summary import summarize_candidate_readiness
from core.opportunity_score import (
    OPPORTUNITY_SCORE_BLOCKED_ZERO,
    OPPORTUNITY_SCORE_COMPRESSION_WARNING,
    OPPORTUNITY_SCORE_EMPTY_INPUT,
    OPPORTUNITY_SCORE_READINESS_INVALID,
    OPPORTUNITY_SCORE_SCHEMA_VERSION,
    OPPORTUNITY_SCORE_SOURCE,
    SCORE_COMPONENT_KEYS,
    score_opportunities,
)
from core.regime_state import REGIME_BULL_TREND, REGIME_RANGE_BOUND
from core.strategy_candidate_classification import classify_strategy_candidates
from core.strategy_candidate_normalization import normalize_strategy_candidates
from core.strategy_candidate_pool import build_strategy_candidate_pool
from core.strategy_spec import DIRECTION_BUY_CALL, FAMILY_VWAP, StrategySpec


def _spec(instruments=("NIFTY",), evidence_keys=None):
    return StrategySpec(
        strategy_id="sample_strategy",
        name="Sample Strategy",
        family=FAMILY_VWAP,
        module_path="strategies.sample",
        callable_name="generate_signal",
        instruments=instruments,
        declared_regimes=(REGIME_BULL_TREND, REGIME_RANGE_BOUND),
        blocked_regimes=("UNKNOWN", "OUT_OF_SESSION", "LIQUIDITY_STRESSED"),
        required_market_state_dimensions=(
            "trend",
            "volatility",
            "breadth",
            "liquidity",
            "session",
        ),
        required_evidence_keys=evidence_keys
        or ("market_state", "regime_state", "feed_health_truth", "quote_truth"),
        direction_capabilities=(DIRECTION_BUY_CALL,),
        min_market_state_confidence=0.6,
        description="Sample metadata",
    )


def _evidence_keys():
    return (
        "market_state",
        "regime_state",
        "feed_health_truth",
        "quote_truth",
        "strategy_quality_audit",
        "paper_outcome_journal",
    )


def _downgrade_report(*, spec=None, instruments=("NIFTY",)):
    pool = build_strategy_candidate_pool(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[spec or _spec(instruments=instruments)],
    )
    normalized = normalize_strategy_candidates(pool)
    classified = classify_strategy_candidates(normalized)
    return apply_candidate_hard_downgrades(classified)


def test_pr73_scores_ready_candidates_with_all_components():
    report = score_opportunities(_downgrade_report(instruments=("BANKNIFTY", "NIFTY")))

    assert report.valid is True
    assert report.schema_version == OPPORTUNITY_SCORE_SCHEMA_VERSION
    assert report.source == OPPORTUNITY_SCORE_SOURCE
    assert report.scored_candidate_ids == (
        "sample_strategy:banknifty:buy_call:bull_trend",
        "sample_strategy:nifty:buy_call:bull_trend",
    )
    for score in report.scores:
        assert 0.0 < score.score <= 100.0
        assert tuple(score.component_scores) == SCORE_COMPONENT_KEYS
        assert tuple(score.weighted_contributions) == SCORE_COMPONENT_KEYS


def test_pr73_payload_is_read_only_and_not_ranking_or_selection():
    payload = json.loads(score_opportunities(_downgrade_report()).to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["roadmap_item"] == "PR73"
    assert payload["metadata"]["roadmap_title"] == "Opportunity Score V1"
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_select_candidates"] is True
    assert "rank" not in payload
    assert "selected_candidate_id" not in payload


def test_pr73_component_overrides_create_score_separation_without_ranking():
    report = score_opportunities(
        _downgrade_report(instruments=("BANKNIFTY", "NIFTY")),
        component_overrides={
            "sample_strategy:nifty:buy_call:bull_trend": {
                key: 0.95 for key in SCORE_COMPONENT_KEYS
            },
            "sample_strategy:banknifty:buy_call:bull_trend": {
                key: 0.30 for key in SCORE_COMPONENT_KEYS
            },
        },
    )

    nifty = report.get("sample_strategy:nifty:buy_call:bull_trend")
    banknifty = report.get("sample_strategy:banknifty:buy_call:bull_trend")

    assert nifty is not None
    assert banknifty is not None
    assert nifty.score > banknifty.score
    assert report.score_compressed is False
    assert report.scored_candidate_ids == (
        "sample_strategy:banknifty:buy_call:bull_trend",
        "sample_strategy:nifty:buy_call:bull_trend",
    )


def test_pr73_flags_score_compression_when_scores_are_too_close():
    report = score_opportunities(_downgrade_report(instruments=("BANKNIFTY", "NIFTY")))

    assert report.score_compressed is True
    assert OPPORTUNITY_SCORE_COMPRESSION_WARNING in report.warnings


def test_pr73_advisory_scores_are_capped():
    report = score_opportunities(
        _downgrade_report(
            spec=_spec(evidence_keys=("market_state", "regime_state")),
        )
    )

    assert report.scores[0].decision == "ADVISORY_ONLY"
    assert report.scores[0].score <= 40.0


def test_pr73_blocked_candidates_get_zero_score():
    downgrade = apply_candidate_hard_downgrades(
        classify_strategy_candidates(
            (
                {
                    "canonical_candidate_id": "bad",
                    "strategy_id": "",
                    "instrument": "NIFTY",
                    "regime": REGIME_BULL_TREND,
                    "direction": DIRECTION_BUY_CALL,
                    "family": FAMILY_VWAP,
                    "required_evidence_keys": _evidence_keys(),
                },
            )
        )
    )

    report = score_opportunities(downgrade)
    blocked_score = report.blocked_scores[0]

    assert report.scores == ()
    assert blocked_score.canonical_candidate_id == "bad"
    assert blocked_score.score == 0.0
    assert OPPORTUNITY_SCORE_BLOCKED_ZERO in blocked_score.blockers


def test_pr73_fails_closed_on_empty_input():
    report = score_opportunities(())

    assert report.valid is False
    assert report.scores == ()
    assert report.blockers == (OPPORTUNITY_SCORE_EMPTY_INPUT,)


def test_pr73_fails_closed_when_readiness_summary_is_invalid():
    report = score_opportunities(
        _downgrade_report(),
        readiness_summary=summarize_candidate_readiness(()),
    )

    assert report.valid is False
    assert OPPORTUNITY_SCORE_READINESS_INVALID in report.blockers
    assert all(score.score == 0.0 for score in report.blocked_scores)
