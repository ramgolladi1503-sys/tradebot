from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
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


def _candidate(direction="BUY_CALL", blockers=()):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=f"unit_{direction.lower()}",
        movement_type="COMPRESSION_BREAKOUT",
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

    assert assessment.no_trade is True
    assert any(signal.reason == "NO_TRADE_CONFLICTING_SIGNALS" for signal in assessment.signals)
    assert "CONFLICTING_TRAP_SIGNAL" in assessment.blockers


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


def test_assess_no_trade_detects_pool_level_baseline_weakness():
    candidates = [
        _candidate("BUY_CALL"),
        _candidate("BUY_CALL"),
        _candidate("BUY_PUT"),
    ]
    for candidate in candidates:
        candidate.evidence["baseline_verdict"] = "UNDERPERFORMS"
        candidate.evidence["baseline_penalty_or_boost"] = -0.08

    assessment = assess_no_trade(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.7),
        candidates=candidates,
    )

    assert assessment.no_trade is True
    assert any(signal.reason == "NO_TRADE_BASELINE_WEAKNESS" for signal in assessment.signals)


def test_generate_no_trade_candidate_emits_no_trade_status():
    candidates = generate_no_trade_candidates(_context(), _regime(primary="CHOP", CHOP=0.85))

    assert len(candidates) == 1
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
