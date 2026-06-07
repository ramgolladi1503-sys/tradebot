from __future__ import annotations

from core.candidate_pool_quality import analyze_candidate_pool
from core.no_trade_engine import assess_no_trade
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult


def _row(**overrides):
    row = {
        "candidate_id": "cand-1",
        "trade_id": "trade-1",
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "movement_type": "COMPRESSION_BREAKOUT",
        "direction": "BUY",
        "option_type": "CE",
        "signal_direction": "BULLISH",
        "regime": "TREND",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_truth_state": "EXEMPLAR",
        "reportable_executable": True,
        "execution_allowed": True,
        "expectancy_status": "KEEP",
        "fallback_used": False,
        "edge_rank_score": 0.8,
        "rank_score": 0.7,
    }
    row.update(overrides)
    return row


def _strategy_candidate(*, strategy_id: str, direction: str, symbol: str = "NIFTY", movement_type: str = "LEGACY_SIGNAL", status: str = "VALIDATED_CANDIDATE", blockers=()):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type=movement_type,
        symbol=symbol,
        direction=direction,
        status=status,
        raw_score=0.7,
        confidence_score=0.7,
        price_structure_score=0.7,
        option_confirmation_score=0.7,
        liquidity_score=0.8,
        freshness_score=0.9,
        volatility_score=0.5,
        regime_alignment_score=0.7,
        timing_score=0.7,
        blockers=tuple(blockers),
    )


def _context(**overrides):
    payload = {
        "symbol": "NIFTY",
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
        "ce_premium_change": 12.0,
        "pe_premium_change": -1.0,
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


def test_pool_quality_scores_diverse_pool_higher_than_duplicate_pool():
    diverse = analyze_candidate_pool(
        [
            _row(candidate_id="cand-bull", trade_id="trade-bull", symbol="NIFTY", strategy_family="breakout", direction="BUY_CALL", option_type="CE", signal_direction="BUY_CALL", edge_rank_score=0.92),
            _row(candidate_id="cand-bear", trade_id="trade-bear", symbol="BANKNIFTY", strategy_family="mean_reversion", direction="BUY_PUT", option_type="PE", signal_direction="BUY_PUT", edge_rank_score=0.88),
            _row(candidate_id="cand-range", trade_id="trade-range", symbol="FINNIFTY", strategy_family="mean_reversion", movement_type="MEAN_REVERSION_EXTENSION", direction="BUY_CALL", option_type="CE", signal_direction="RANGE", regime="RANGE", edge_rank_score=0.84, expectancy_status="WATCH"),
        ]
    )
    duplicate = analyze_candidate_pool(
        [
            _row(candidate_id="cand-1", trade_id="trade-1", symbol="NIFTY", strategy_family="breakout", direction="BUY_CALL", option_type="CE", signal_direction="BUY_CALL", edge_rank_score=0.92),
            _row(candidate_id="cand-2", trade_id="trade-2", symbol="NIFTY", strategy_family="breakout", direction="BUY_CALL", option_type="CE", signal_direction="BUY_CALL", edge_rank_score=0.90),
            _row(candidate_id="cand-3", trade_id="trade-3", symbol="NIFTY", strategy_family="breakout", direction="BUY_CALL", option_type="CE", signal_direction="BUY_CALL", edge_rank_score=0.88, fallback_used=True),
        ]
    )

    assert diverse.quality_score > duplicate.quality_score
    assert diverse.readiness_state == "DIVERSE"
    assert duplicate.readiness_state in {"THIN", "CONCENTRATED", "FALLBACK_HEAVY", "ONE_SIDED"}


def test_fallback_heavy_pool_is_low_quality_and_no_trade():
    assessment = assess_no_trade(
        _context(fallback_used=False),
        _regime(primary="TREND_UP", TREND_UP=0.7),
        candidates=[
            _strategy_candidate(strategy_id="a", direction="BUY_CALL"),
            _strategy_candidate(strategy_id="b", direction="BUY_CALL", status="BLOCKED_CANDIDATE", blockers=("FALLBACK_QUOTE_ONLY",)),
            _strategy_candidate(strategy_id="c", direction="BUY_CALL", status="BLOCKED_CANDIDATE", blockers=("FALLBACK_QUOTE_ONLY",)),
        ],
    )

    assert assessment.no_trade is True
    assert any(signal.reason == "NO_TRADE_POOL_CONCENTRATION" for signal in assessment.signals)


def test_thin_pool_with_one_weak_candidate_is_conservative():
    report = analyze_candidate_pool(
        [
            _row(
                candidate_id="cand-weak",
                trade_id="trade-weak",
                symbol="NIFTY",
                strategy_family="breakout",
                direction="BUY",
                edge_rank_score=0.31,
                rank_score=0.24,
                expectancy_status="INSUFFICIENT_DATA",
                execution_allowed=False,
                reportable_executable=False,
                permission="QUEUE_ONLY",
                final_action="QUEUE_ONLY",
            )
        ]
    )

    assert report.quality_score < 0.5
    assert report.readiness_state == "THIN"
    assert report.executable_count == 0
    assert report.advisory_count == 0


def test_pool_quality_is_deterministic():
    pool = [
        _row(candidate_id="cand-a", trade_id="trade-a", symbol="NIFTY", strategy_family="breakout", direction="BUY", edge_rank_score=0.81),
        _row(candidate_id="cand-b", trade_id="trade-b", symbol="BANKNIFTY", strategy_family="mean_reversion", direction="SELL", edge_rank_score=0.79),
    ]

    first = analyze_candidate_pool(pool)
    second = analyze_candidate_pool(pool)

    first_dict = first.to_dict()
    second_dict = second.to_dict()
    first_dict.pop("generated_epoch", None)
    second_dict.pop("generated_epoch", None)
    assert first_dict == second_dict


def test_range_pool_counts_range_coverage_without_bullish_only_bias():
    report = analyze_candidate_pool(
        [
            _row(
                candidate_id="cand-range-a",
                trade_id="trade-range-a",
                symbol="NIFTY",
                strategy_family="mean_reversion",
                movement_type="MEAN_REVERSION_EXTENSION",
                direction="BUY_CALL",
                option_type="CE",
                signal_direction="RANGE",
                regime="RANGE",
            ),
            _row(
                candidate_id="cand-range-b",
                trade_id="trade-range-b",
                symbol="BANKNIFTY",
                strategy_family="mean_reversion",
                movement_type="OPENING_RANGE_RETEST",
                direction="BUY_PUT",
                option_type="PE",
                signal_direction="RANGE",
                regime="RANGE",
            ),
        ]
    )

    assert report.range_count == 2
    assert report.bullish_count == 0
    assert report.bearish_count == 0
    assert report.quality_score > 0.5
