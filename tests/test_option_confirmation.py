from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.option_confirmation import assess_option_pressure, confirm_candidate_option_pressure
from strategies.movement.option_pressure import generate_option_pressure_candidates


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
        strategy_id="unit_candidate",
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


def test_assess_option_pressure_detects_bullish_dominance():
    assessment = assess_option_pressure(_context())

    assert assessment.dominant_direction == "BUY_CALL"
    assert assessment.bullish_score > assessment.bearish_score
    assert assessment.ce.pressure_score > assessment.pe.pressure_score
    assert assessment.blockers == ("OPTION_CONFIRMATION_MISSING",)
    assert assessment.to_dict()["dominant_direction"] == "BUY_CALL"


def test_assess_option_pressure_detects_bearish_dominance():
    assessment = assess_option_pressure(
        _context(
            ce_premium_change=-1.0,
            pe_premium_change=16.0,
            option_pe_ltp=140.0,
            pe_depth=1400.0,
        )
    )

    assert assessment.dominant_direction == "BUY_PUT"
    assert assessment.bearish_score > assessment.bullish_score
    assert assessment.pe.pressure_score > assessment.ce.pressure_score


def test_assess_option_pressure_returns_neutral_when_sides_are_balanced():
    assessment = assess_option_pressure(
        _context(
            ce_premium_change=10.0,
            pe_premium_change=10.0,
            option_ce_ltp=120.0,
            option_pe_ltp=120.0,
            ce_depth=1000.0,
            pe_depth=1000.0,
        )
    )

    assert assessment.dominant_direction == "NEUTRAL"
    assert "no_dominant_option_pressure" in assessment.warnings


def test_confirm_candidate_option_pressure_promotes_matching_candidate():
    confirmation = confirm_candidate_option_pressure(_candidate("BUY_CALL"), _context())

    assert confirmation.suggested_effect == "PROMOTE"
    assert confirmation.dominant_direction == "BUY_CALL"
    assert confirmation.confirmation_score > confirmation.opposing_score
    assert confirmation.blockers == ()


def test_confirm_candidate_option_pressure_demotes_opposing_candidate():
    confirmation = confirm_candidate_option_pressure(_candidate("BUY_PUT"), _context())

    assert confirmation.suggested_effect == "BLOCK"
    assert confirmation.dominant_direction == "BUY_CALL"
    assert "OPTION_CONFIRMATION_MISSING" in confirmation.blockers


def test_confirm_candidate_option_pressure_blocks_candidate_existing_blockers():
    confirmation = confirm_candidate_option_pressure(
        _candidate("BUY_CALL", blockers=("STALE_OPTION_LTP",)),
        _context(),
    )

    assert confirmation.suggested_effect == "BLOCK"
    assert "STALE_OPTION_LTP" in confirmation.blockers
    assert "candidate_already_hard_blocked" in confirmation.warnings


def test_option_pressure_strategy_generates_validated_dominant_candidate():
    candidates = generate_option_pressure_candidates(
        _context(),
        _regime(TREND_UP=0.7, VOLATILITY_EXPANSION=0.3),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == "option_pressure_confirmation_v1"
    assert candidate.movement_type == "OPTION_PRESSURE_CONFIRMATION"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "VALIDATED_CANDIDATE"
    assert candidate.executable_eligible is True
    assert "confirmation_layer_not_execution_signal" in candidate.suppression_tags


def test_option_pressure_strategy_returns_empty_for_neutral_pressure():
    candidates = generate_option_pressure_candidates(
        _context(ce_premium_change=10.0, pe_premium_change=10.0),
        _regime(),
    )

    assert candidates == ()


def test_option_pressure_strategy_blocks_bad_quote_quality():
    candidates = generate_option_pressure_candidates(
        _context(
            fallback_used=True,
            quote_source="recovered_fallback",
            ce_spread_pct=9.0,
            option_ltp_age_sec=8.0,
        ),
        _regime(TREND_UP=0.6),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status == "BLOCKED_CANDIDATE"
    assert candidate.executable_eligible is False
    assert set(candidate.blockers) >= {
        "FALLBACK_QUOTE_ONLY",
        "WIDE_SPREAD",
        "STALE_OPTION_LTP",
    }
