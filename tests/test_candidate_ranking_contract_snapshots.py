from __future__ import annotations

import json
from pathlib import Path

from core.candidate_ranking import rank_candidates
from core.directional_balance import analyze_directional_balance
from core.opportunity_scoring import (
    ADVISORY_ONLY,
    NEEDS_CONFIRMATION,
    NO_TRADE_ONLY,
    SCORE_ELIGIBLE,
    SUPPRESSED_BY_DOWNGRADE,
    OpportunityScoreBreakdown,
    OpportunityScoreRecord,
    OpportunityScoreReport,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "candidate_ranking_contract"


def _breakdown(final_score=0.5):
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


def _score(
    strategy_id="s1",
    *,
    symbol="NIFTY",
    direction="BUY_CALL",
    movement_type="COMPRESSION_BREAKOUT",
    final_score=0.5,
    eligibility=SCORE_ELIGIBLE,
    bucket=None,
    executable_candidate=None,
    downgrade_reasons=(),
    blockers=(),
    warnings=(),
    safety_flags=(),
):
    if bucket is None:
        bucket = {
            SCORE_ELIGIBLE: "EXECUTABLE_CANDIDATE",
            NEEDS_CONFIRMATION: "NEAR_EXECUTABLE_CANDIDATE",
            ADVISORY_ONLY: "ADVISORY_CANDIDATE",
            SUPPRESSED_BY_DOWNGRADE: "SUPPRESSED_CANDIDATE",
            NO_TRADE_ONLY: "NO_TRADE_CANDIDATE",
        }[eligibility]
    if executable_candidate is None:
        executable_candidate = eligibility == SCORE_ELIGIBLE
    return OpportunityScoreRecord(
        strategy_id=strategy_id,
        symbol=symbol,
        direction=direction,
        movement_type=movement_type,
        bucket=bucket,
        score_eligibility=eligibility,
        final_score=final_score,
        executable_candidate=executable_candidate,
        score_explanation="unit",
        downgrade_reasons=downgrade_reasons,
        safety_flags=safety_flags,
        blockers=blockers,
        warnings=warnings,
        breakdown=_breakdown(final_score),
    )


def _report(scores):
    return OpportunityScoreReport(
        schema_version=1,
        read_only=True,
        is_order_action=False,
        append=False,
        score_count=len(scores),
        score_eligible_count=sum(1 for item in scores if item.score_eligibility == SCORE_ELIGIBLE),
        needs_confirmation_count=sum(1 for item in scores if item.score_eligibility == NEEDS_CONFIRMATION),
        advisory_count=sum(1 for item in scores if item.score_eligibility == ADVISORY_ONLY),
        suppressed_count=sum(1 for item in scores if item.score_eligibility == SUPPRESSED_BY_DOWNGRADE),
        no_trade_count=sum(1 for item in scores if item.score_eligibility == NO_TRADE_ONLY),
        scores=tuple(scores),
        blockers=tuple(sorted(set(blocker for item in scores for blocker in item.blockers))),
        warnings=tuple(sorted(set(warning for item in scores for warning in item.warnings))),
        safety_flags=tuple(sorted(set(flag for item in scores for flag in item.safety_flags))),
        metadata={"scorer": "opportunity_score_v1"},
    )


def _load_snapshot(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _rank_summary(rank) -> dict:
    return {
        "rank": rank.rank,
        "strategy_id": rank.strategy_id,
        "symbol": rank.symbol,
        "direction": rank.direction,
        "directional_family": rank.directional_family,
        "movement_type": rank.movement_type,
        "final_score": rank.final_score,
        "bucket": rank.bucket,
        "score_eligibility": rank.score_eligibility,
        "executable_candidate": rank.executable_candidate,
        "rank_reason": rank.rank_reason,
        "downgrade_reasons": sorted(rank.downgrade_reasons),
        "blockers": sorted(rank.blockers),
        "warnings": sorted(rank.warnings),
        "safety_flags": sorted(rank.safety_flags),
        "directional_warnings": sorted(rank.directional_warnings),
    }


def _stable_report_summary(report) -> dict:
    return {
        "schema_version": report.schema_version,
        "read_only": report.read_only,
        "is_order_action": report.is_order_action,
        "append": report.append,
        "rank_count": report.rank_count,
        "executable_count": report.executable_count,
        "near_executable_count": report.near_executable_count,
        "advisory_count": report.advisory_count,
        "suppressed_count": report.suppressed_count,
        "no_trade_count": report.no_trade_count,
        "blockers": sorted(report.blockers),
        "warnings": sorted(report.warnings),
        "safety_flags": sorted(report.safety_flags),
        "directional_imbalance_flags": sorted(report.directional_imbalance_flags),
        "metadata": {
            "ranker": report.metadata.get("ranker"),
            "scope": report.metadata.get("scope"),
            "source_scorer": report.metadata.get("source_scorer"),
            "source_directional_balance": report.metadata.get("source_directional_balance"),
        },
        "ranks": [_rank_summary(rank) for rank in report.ranks],
    }


def test_clean_balanced_ranking_contract_snapshot():
    score_report = _report(
        [
            _score("put_mid", direction="BUY_PUT", movement_type="TREND_PULLBACK", final_score=0.61),
            _score("call_high", direction="BUY_CALL", movement_type="COMPRESSION_BREAKOUT", final_score=0.82),
        ]
    )
    balance = analyze_directional_balance(score_report)

    report = rank_candidates(score_report, balance)
    summary = _stable_report_summary(report)

    assert summary == _load_snapshot("clean_ranking_report.json")
    assert [rank["strategy_id"] for rank in summary["ranks"]] == ["call_high", "put_mid"]
    assert summary["read_only"] is True
    assert summary["is_order_action"] is False
    assert summary["append"] is False


def test_safety_ordering_ranking_contract_snapshot():
    report = rank_candidates(
        _report(
            [
                _score("suppressed", final_score=0.99, eligibility=SUPPRESSED_BY_DOWNGRADE,
                       downgrade_reasons=("fallback_quote_data",), blockers=("FALLBACK_QUOTE_ONLY",),
                       safety_flags=("fallback_data",)),
                _score("no_trade", direction="NO_TRADE", movement_type="NO_TRADE_CHOP", final_score=0.0,
                       eligibility=NO_TRADE_ONLY, downgrade_reasons=("candidate_is_no_trade_signal",),
                       blockers=("NO_TRADE_CHOP",)),
                _score("advisory", final_score=0.35, eligibility=ADVISORY_ONLY, warnings=("context_only",)),
                _score("near", final_score=0.64, eligibility=NEEDS_CONFIRMATION),
                _score("exec", final_score=0.55, eligibility=SCORE_ELIGIBLE),
            ]
        )
    )
    summary = _stable_report_summary(report)

    assert summary == _load_snapshot("safety_ordering_report.json")
    assert [rank["strategy_id"] for rank in summary["ranks"]] == ["exec", "near", "advisory", "suppressed", "no_trade"]
    assert summary["ranks"][3]["final_score"] == 0.99
    assert summary["ranks"][3]["score_eligibility"] == SUPPRESSED_BY_DOWNGRADE


def test_directional_warning_ranking_contract_snapshot():
    score_report = _report(
        [
            _score("call_b", direction="CE", final_score=0.60),
            _score("call_a", direction="BUY_CALL", final_score=0.80),
        ]
    )
    balance = analyze_directional_balance(score_report)

    report = rank_candidates(score_report, balance)
    summary = _stable_report_summary(report)

    assert summary == _load_snapshot("directional_warning_report.json")
    assert summary["rank_count"] == 2
    assert all(rank["directional_family"] == "BULLISH" for rank in summary["ranks"])
    assert not any(rank["directional_family"] == "BEARISH" for rank in summary["ranks"])
    assert "missing_bearish_candidate_coverage" in summary["directional_imbalance_flags"]


def test_ranking_contract_required_top_level_keys_are_stable():
    report = rank_candidates(_report([_score("clean", final_score=0.7)]))
    payload = report.to_dict()

    assert set(payload) >= {
        "schema_version",
        "read_only",
        "is_order_action",
        "append",
        "rank_count",
        "executable_count",
        "near_executable_count",
        "advisory_count",
        "suppressed_count",
        "no_trade_count",
        "ranks",
        "blockers",
        "warnings",
        "safety_flags",
        "directional_imbalance_flags",
        "metadata",
    }
    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["metadata"]["scope"] == "read_only_no_execution_no_score_mutation"
