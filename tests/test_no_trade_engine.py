from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.candidate_pool_quality import analyze_candidate_pool
from core.expectancy.edge_ranking import apply_edge_ranking
from core.no_trade_engine import assess_no_trade, check_no_trade_conditions
from strategies.movement.no_trade_chop import generate_no_trade_candidates


def _regime(primary="RANGE", **scores):
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


def _candidate(direction="BUY_CALL", blockers=(), movement_type="COMPRESSION_BREAKOUT"):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=f"unit_{direction.lower()}",
        movement_type=movement_type,
        symbol="NIFTY",
        direction=direction,
        status="VALIDATED_CANDIDATE" if not blockers else "BLOCKED_CANDIDATE",
        raw_score=0.7,
        confidence_score=0.7,
        price_structure_score=0.7,
        option_confirmation_score=0.7,
        liquidity_score=0.8,
        freshness_score=0.9,
        volatility_score=0.5,
        regime_alignment_score=0.7,
        entry_trigger="unit",
        invalid_if="unit",
        rank_reason="unit",
        blockers=blockers,
    )


def test_assess_no_trade_detects_chop():
    assessment = assess_no_trade(_context(), _regime(primary="CHOP", CHOP=0.8, RANGE=0.7))

    assert assessment.no_trade is True
    assert assessment.primary_reason == "NO_TRADE_CHOP"
    assert "NO_TRADE_CHOP" in assessment.blockers
    assert assessment.signals[0].reason == "NO_TRADE_CHOP"


def test_assess_no_trade_detects_stale_fallback_and_liquidity_issues():
    assessment = assess_no_trade(
        _context(
            fallback_used=True,
            quote_source="recovered_fallback",
            option_ltp_age_sec=8.0,
            ce_spread_pct=9.0,
            pe_spread_pct=9.0,
            ce_depth=None,
            pe_depth=0.0,
        ),
        _regime(primary="TREND_UP", TREND_UP=0.7),
    )

    reasons = {signal.reason for signal in assessment.signals}
    assert "NO_TRADE_FALLBACK_DATA" in reasons
    assert "NO_TRADE_STALE_FEED" in reasons
    assert "NO_TRADE_LIQUIDITY" in reasons
    assert set(assessment.blockers) >= {
        "FALLBACK_QUOTE_ONLY",
        "STALE_OPTION_LTP",
        "WIDE_SPREAD",
        "MISSING_DEPTH",
    }


def test_assess_no_trade_detects_weak_option_confirmation():
    assessment = assess_no_trade(
        _context(ce_premium_change=0.0, pe_premium_change=0.0),
        _regime(primary="RANGE", RANGE=0.5),
    )

    assert assessment.no_trade is True
    assert any(signal.reason == "NO_TRADE_WEAK_OPTION_CONFIRMATION" for signal in assessment.signals)
    assert "OPTION_CONFIRMATION_MISSING" in assessment.blockers


def test_assess_no_trade_detects_conflicting_candidates():
    assessment = assess_no_trade(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.7),
        candidates=[_candidate("BUY_CALL"), _candidate("BUY_PUT")],
    )

    assert assessment.no_trade is False
    assert assessment.primary_reason == "TRADE_ALLOWED"
    assert assessment.blockers == ()


def test_bearish_mixed_pool_does_not_fail_closed_but_penalizes_mismatched_candidate():
    bearish_row = {
        "trade_id": "T-BEARISH",
        "candidate_id": "C-BEARISH",
        "symbol": "NIFTY",
        "strategy_family": "mean_reversion",
        "regime": "TREND_DOWN",
        "direction": "BUY_PUT",
        "option_type": "PE",
        "signal_direction": "BUY_PUT",
        "movement_type": "MEAN_REVERSION_EXTENSION",
        "expectancy_status": "KEEP",
        "expectancy_sample_count": 60,
        "expectancy_avg_cost_adjusted_r": 0.20,
        "liquidity_score": 0.82,
        "timing_score": 0.74,
        "regime_fit": 0.79,
        "rr_score": 0.68,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "execution_status": "executable",
        "reportable_executable": True,
        "execution_allowed": True,
        "eligible_for_execution": True,
        "selected_for_execution": True,
        "candidate_status": "executable",
        "candidate_class": "primary",
        "candidate_type": "directional",
        "quote_source": "tick_store",
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
    }
    bullish_row = dict(bearish_row, trade_id="T-BULLISH", candidate_id="C-BULLISH", direction="BUY_CALL", option_type="CE", signal_direction="BUY_CALL")
    assessment = assess_no_trade(
        _context(),
        _regime(primary="TREND_DOWN", TREND_DOWN=0.7),
        candidates=[
            _candidate("BUY_PUT"),
            _candidate("BUY_CALL"),
        ],
    )

    pool = analyze_candidate_pool([bearish_row, bullish_row])
    ranked_bearish = apply_edge_ranking(bearish_row)
    ranked_bullish = apply_edge_ranking(bullish_row)

    assert pool.bearish_count == 1
    assert pool.bullish_count == 1
    assert assessment.no_trade is False
    assert assessment.primary_reason == "TRADE_ALLOWED"
    assert assessment.blockers == ()
    assert ranked_bearish["edge_rank_score"] > ranked_bullish["edge_rank_score"]
    assert ranked_bullish["edge_rank_components"]["candidate_regime_mismatch_penalty"] > 0.0


def test_chop_directional_heavy_pool_prefers_no_trade():
    assessment = assess_no_trade(
        _context(),
        _regime(primary="CHOP", CHOP=0.82, RANGE=0.12),
        candidates=[
            _candidate("BUY_CALL"),
            _candidate("BUY_CALL"),
            _candidate("BUY_PUT"),
        ],
    )

    assert assessment.no_trade is True
    assert assessment.primary_reason in {"NO_TRADE_CHOP", "NO_TRADE_POOL_CONCENTRATION"}
    assert any(signal.reason in {"NO_TRADE_CHOP", "NO_TRADE_POOL_CONCENTRATION"} for signal in assessment.signals)


def test_assess_no_trade_allows_clean_context():
    assessment = assess_no_trade(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.7, CHOP=0.1),
        candidates=[_candidate("BUY_CALL")],
    )

    assert assessment.no_trade is False
    assert assessment.primary_reason == "TRADE_ALLOWED"
    assert assessment.blockers == ()
    assert assessment.signals == ()


def test_range_regime_with_range_candidate_does_not_fail_closed():
    range_row = {
        "trade_id": "T-RANGE",
        "candidate_id": "C-RANGE",
        "symbol": "NIFTY",
        "strategy_family": "mean_reversion",
        "regime": "RANGE",
        "direction": "BUY_CALL",
        "option_type": "CE",
        "signal_direction": "RANGE",
        "movement_type": "MEAN_REVERSION_EXTENSION",
        "expectancy_status": "KEEP",
        "expectancy_sample_count": 60,
        "expectancy_avg_cost_adjusted_r": 0.16,
        "liquidity_score": 0.82,
        "timing_score": 0.74,
        "regime_fit": 0.79,
        "rr_score": 0.68,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "execution_status": "executable",
        "reportable_executable": True,
        "execution_allowed": True,
        "eligible_for_execution": True,
        "selected_for_execution": True,
        "candidate_status": "executable",
        "candidate_class": "primary",
        "candidate_type": "range",
        "quote_source": "tick_store",
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
    }
    assessment = assess_no_trade(
        _context(),
        _regime(primary="RANGE", RANGE=0.75, CHOP=0.05),
        candidates=[
            _candidate("BUY_CALL", movement_type="MEAN_REVERSION_EXTENSION"),
            _candidate("BUY_PUT", movement_type="OPENING_RANGE_RETEST"),
        ],
    )

    pool = analyze_candidate_pool([range_row])
    assert assessment.no_trade is False
    assert assessment.primary_reason == "TRADE_ALLOWED"
    assert pool.range_count == 1


def test_generate_no_trade_candidate_emits_no_trade_status():
    candidates = generate_no_trade_candidates(_context(), _regime(primary="CHOP", CHOP=0.85))

    assert candidates
    candidate = candidates[0]
    assert candidate.strategy_id == "no_trade_engine_v1"
    assert candidate.movement_type == "NO_TRADE_CHOP"
    assert candidate.direction == "NO_TRADE"
    assert candidate.status == "NO_TRADE"
    assert candidate.executable_eligible is False
    assert "no_trade_engine" in candidate.suppression_tags
    assert candidate.evidence["assessment"]["no_trade"] is True


def test_generate_no_trade_candidate_returns_empty_when_clean():
    candidates = generate_no_trade_candidates(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8, CHOP=0.1),
        candidates=[_candidate("BUY_CALL")],
    )

    assert candidates == ()


def test_legacy_check_no_trade_conditions_shape_is_preserved(monkeypatch):
    class FixedDateTime:
        @staticmethod
        def time():
            from datetime import time

            return time(10, 30)

    monkeypatch.setattr("core.no_trade_engine.now_ist", lambda: FixedDateTime())
    monkeypatch.setattr("core.no_trade_engine.get_nifty_ltp", lambda: 22500.0)
    monkeypatch.setattr("core.no_trade_engine.get_index_vwap", lambda symbol: 22400.0)

    result = check_no_trade_conditions()

    assert set(result) == {"allowed", "reason"}
    assert result["allowed"] is True
    assert result["reason"] == "Trade allowed"
