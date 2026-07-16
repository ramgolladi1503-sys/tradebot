from __future__ import annotations

import json
from pathlib import Path

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.ranking_orchestrator import build_ranked_opportunity_report

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ranked_pipeline_contract"


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


def _context(**overrides):
    payload = {
        "symbol": "NIFTY",
        "spot_ltp": 22550.0,
        "vwap": 22500.0,
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
        "ce_premium_change": 14.0,
        "pe_premium_change": -2.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.9,
        "ce_depth": 1200.0,
        "pe_depth": 1000.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def _candidate(
    strategy_id="candidate",
    *,
    direction="BUY_CALL",
    movement_type="COMPRESSION_BREAKOUT",
    status="RAW_CANDIDATE",
    blockers=(),
    warnings=(),
    raw_score=0.75,
    confidence_score=0.75,
    price_structure_score=0.8,
    option_confirmation_score=None,
    liquidity_score=None,
    freshness_score=None,
    volatility_score=0.5,
    regime_alignment_score=0.8,
    timing_score=0.7,
    trap_risk_score=0.05,
    confluence_score=0.6,
):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type=movement_type,
        symbol="NIFTY",
        direction=direction,
        status=status,
        raw_score=raw_score,
        confidence_score=confidence_score,
        price_structure_score=price_structure_score,
        option_confirmation_score=option_confirmation_score,
        liquidity_score=liquidity_score,
        freshness_score=freshness_score,
        volatility_score=volatility_score,
        regime_alignment_score=regime_alignment_score,
        timing_score=timing_score,
        trap_risk_score=trap_risk_score,
        confluence_score=confluence_score,
        entry_trigger="unit",
        invalid_if="unit",
        rank_reason="unit",
        lineage={"promotion_state": "PROMOTED"},
        blockers=blockers,
        warnings=warnings,
    )


def _generator(*candidates):
    def _inner(ctx, regime):
        return candidates

    return _inner


def _load_snapshot(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _rank_summary(rank) -> dict:
    return {
        "rank": rank.rank,
        "strategy_id": rank.strategy_id,
        "final_score": rank.final_score,
        "bucket": rank.bucket,
        "score_eligibility": rank.score_eligibility,
        "directional_family": rank.directional_family,
        "directional_warnings": sorted(rank.directional_warnings),
    }


def _stable_report_summary(report) -> dict:
    return {
        "schema_version": report.schema_version,
        "symbol": report.symbol,
        "read_only": report.read_only,
        "is_order_action": report.is_order_action,  # proof: is_order_action=False
        "append": report.append,
        "pipeline_stage_order": list(report.pipeline_stage_order),
        "raw_candidate_count": report.raw_candidate_count,
        "normalized_candidate_count": report.normalized_candidate_count,
        "ranked_candidate_count": report.ranked_candidate_count,
        "top_rank_strategy_id": report.top_rank_strategy_id,
        "top_rank_score": report.top_rank_score,
        "executable_rank_count": report.executable_rank_count,
        "near_executable_rank_count": report.near_executable_rank_count,
        "advisory_rank_count": report.advisory_rank_count,
        "suppressed_rank_count": report.suppressed_rank_count,
        "no_trade_rank_count": report.no_trade_rank_count,
        "blockers": sorted(report.blockers),
        "safety_flags": sorted(report.safety_flags),
        "metadata": {
            "orchestrator": report.metadata.get("orchestrator"),
            "scope": report.metadata.get("scope"),
            "source_candidate_pool": report.metadata.get("source_candidate_pool"),
            "source_normalizer": report.metadata.get("source_normalizer"),
            "source_classifier": report.metadata.get("source_classifier"),
            "source_downgrade_engine": report.metadata.get("source_downgrade_engine"),
            "source_scorer": report.metadata.get("source_scorer"),
            "source_directional_balance": report.metadata.get("source_directional_balance"),
            "source_ranker": report.metadata.get("source_ranker"),
        },
        "stages": {
            "candidate_pool": {
                "candidate_count": report.candidate_pool.candidate_count,
                "movement_candidate_count": report.candidate_pool.movement_candidate_count,
                "no_trade_candidate_count": report.candidate_pool.no_trade_candidate_count,
                "report_executable_eligible_count": report.candidate_pool.report_executable_eligible_count,
                "failed_generator_count": report.candidate_pool.failed_generator_count,
                "no_trade": report.candidate_pool.no_trade_assessment.no_trade,
                "no_trade_primary_reason": report.candidate_pool.no_trade_assessment.primary_reason,
            },
            "normalization": {
                "raw_count": report.normalization.raw_count,
                "normalized_count": report.normalization.normalized_count,
                "duplicate_group_count": report.normalization.duplicate_group_count,
            },
            "classification": {
                "candidate_count": report.classification.candidate_count,
                "executable_count": report.classification.executable_count,
                "suppressed_count": report.classification.suppressed_count,
                "no_trade_count": report.classification.no_trade_count,
            },
            "hard_downgrade": {
                "candidate_count": report.hard_downgrade.candidate_count,
                "executable_after_downgrade_count": report.hard_downgrade.executable_after_downgrade_count,
                "suppressed_count": report.hard_downgrade.suppressed_count,
                "no_trade_count": report.hard_downgrade.no_trade_count,
            },
            "scoring": {
                "score_count": report.scoring.score_count,
                "score_eligible_count": report.scoring.score_eligible_count,
                "suppressed_count": report.scoring.suppressed_count,
                "no_trade_count": report.scoring.no_trade_count,
            },
            "directional_balance": {
                "coverage_state": report.directional_balance.coverage_state,
                "imbalance_flags": sorted(report.directional_balance.imbalance_flags),
            },
            "ranking": {
                "rank_count": report.ranking.rank_count,
                "executable_count": report.ranking.executable_count,
                "suppressed_count": report.ranking.suppressed_count,
                "no_trade_count": report.ranking.no_trade_count,
                "directional_imbalance_flags": sorted(report.ranking.directional_imbalance_flags),
            },
        },
        "ranks": [_rank_summary(rank) for rank in report.ranking.ranks],
    }


def test_clean_bullish_ranked_pipeline_contract_snapshot():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[
            _generator(
                _candidate("call_high", direction="BUY_CALL", price_structure_score=0.9),
                _candidate("call_mid", direction="BUY_CALL", movement_type="TREND_PULLBACK", price_structure_score=0.7),
            )
        ],
        include_strategy_id_in_normalization_key=True,
    )

    summary = _stable_report_summary(report)

    assert summary == _load_snapshot("clean_bullish_pipeline_report.json")
    assert summary["read_only"] is True
    assert summary["is_order_action"] is False
    assert summary["append"] is False
    assert summary["top_rank_strategy_id"] == "call_high"


def test_fallback_no_trade_ranked_pipeline_contract_snapshot():
    executable = _candidate("exec", direction="BUY_CALL", price_structure_score=0.7)
    fallback = _candidate(
        "fallback",
        direction="BUY_PUT",
        status="BLOCKED_CANDIDATE",
        blockers=("FALLBACK_QUOTE_ONLY",),
        warnings=("fallback_used",),
        raw_score=1.0,
        confidence_score=1.0,
        price_structure_score=1.0,
        regime_alignment_score=1.0,
    )
    report = build_ranked_opportunity_report(
        _context(fallback_used=True, quote_source="recovered_fallback"),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(fallback, executable)],
        include_strategy_id_in_normalization_key=True,
    )

    summary = _stable_report_summary(report)

    assert summary == _load_snapshot("fallback_no_trade_pipeline_report.json")
    assert [rank["strategy_id"] for rank in summary["ranks"]] == ["exec", "fallback", "no_trade_engine_v1"]
    assert summary["executable_rank_count"] == 0
    assert summary["no_trade_rank_count"] == 1


def test_empty_ranked_pipeline_contract_snapshot():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator()],
    )

    summary = _stable_report_summary(report)

    assert summary == _load_snapshot("empty_pipeline_report.json")
    assert summary["ranked_candidate_count"] == 0
    assert summary["ranks"] == []


def test_ranked_pipeline_contract_required_top_level_keys_are_stable():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(_candidate("clean", direction="BUY_CALL"))],
        include_strategy_id_in_normalization_key=True,
    )

    payload = report.to_dict()

    assert set(payload) >= {
        "schema_version",
        "symbol",
        "read_only",
        "is_order_action",
        "append",
        "pipeline_stage_order",
        "candidate_pool",
        "normalization",
        "classification",
        "hard_downgrade",
        "scoring",
        "directional_balance",
        "ranking",
        "raw_candidate_count",
        "normalized_candidate_count",
        "ranked_candidate_count",
        "top_rank_strategy_id",
        "top_rank_score",
        "blockers",
        "warnings",
        "safety_flags",
        "metadata",
    }
    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["metadata"]["scope"] == "read_only_no_execution_no_dashboard_no_live_wiring"
