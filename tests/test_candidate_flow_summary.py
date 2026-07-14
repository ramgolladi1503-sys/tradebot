from core.candidate_flow_summary import build_candidate_flow_summary
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.ranking_orchestrator import build_ranked_opportunity_report


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


def _candidate(direction="BUY_CALL", blockers=()):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=f"unit_{direction.lower()}",
        movement_type="COMPRESSION_BREAKOUT",
        symbol="NIFTY",
        direction=direction,
        status="RAW_CANDIDATE" if not blockers else "BLOCKED_CANDIDATE",
        raw_score=0.7,
        confidence_score=0.7,
        price_structure_score=0.7,
        option_confirmation_score=None,
        liquidity_score=None,
        freshness_score=None,
        volatility_score=0.5,
        regime_alignment_score=0.7,
        timing_score=0.7,
        trap_risk_score=0.05,
        confluence_score=0.7,
        entry_trigger="unit",
        invalid_if="unit",
        rank_reason="unit",
        blockers=blockers,
    )


def test_ranked_report_exposes_candidate_flow_summary_for_no_trade_dropoff():
    def generator(ctx, regime):
        return (_candidate("BUY_CALL"),)

    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="CHOP", CHOP=0.85),
        candidate_generators=[generator],
    )

    flow = report.metadata["candidate_flow_summary"]
    assert flow["raw_candidate_count"] == 1
    assert flow["classified_candidate_count"] == 2
    assert flow["scored_candidate_count"] == 2
    assert flow["ranked_candidate_count"] == 2
    assert flow["no_trade_candidate_count"] == 1
    assert flow["no_trade_suppressed_count"] == 1
    assert "NO_TRADE_CHOP" in flow["dominant_blockers"]
    assert report.no_trade_rank_count == 1
    assert report.blockers


def test_flow_summary_counts_are_consistent_with_component_reports():
    def generator(ctx, regime):
        return (_candidate("BUY_CALL"),)

    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[generator],
    )

    pool = report.candidate_pool
    classification = report.classification
    scoring = report.scoring
    ranking = report.ranking
    summary = build_candidate_flow_summary(pool, classification, scoring, ranking)

    assert summary.raw_candidate_count == pool.movement_candidate_count
    assert summary.classified_candidate_count == classification.candidate_count
    assert summary.scored_candidate_count == scoring.score_count
    assert summary.ranked_candidate_count == ranking.rank_count
    assert summary.metadata["candidate_pool_failed_generators"] == 0
