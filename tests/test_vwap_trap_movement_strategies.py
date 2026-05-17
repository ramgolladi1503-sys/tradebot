from core.candidate_pool import build_candidate_pool
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.failed_breakout_trap import generate_failed_breakout_trap_candidates
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates


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


def _base_context(**overrides):
    payload = {
        "symbol": "NIFTY",
        "spot_ltp": 22620.0,
        "open_price": 22500.0,
        "vwap": 22600.0,
        "vwap_slope": 0.04,
        "day_high": 22680.0,
        "day_low": 22480.0,
        "orb_high": 22660.0,
        "orb_low": 22490.0,
        "nearest_resistance": 22670.0,
        "nearest_support": 22580.0,
        "range_width_pct": 0.45,
        "atr_short": 80.0,
        "atr_long": 100.0,
        "volume_z": 1.2,
        "option_ce_ltp": 125.0,
        "option_pe_ltp": 92.0,
        "ce_premium_change": 10.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 65,
        "metadata": {},
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def test_vwap_reclaim_generates_call_candidate_after_confirmed_reclaim():
    ctx = _base_context(metadata={"previous_spot_ltp": 22590.0})
    candidates = generate_vwap_reclaim_rejection_candidates(ctx, _regime(TREND_UP=0.6, CHOP=0.1))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == "vwap_reclaim_rejection_v1"
    assert candidate.movement_type == "VWAP_RECLAIM_REJECTION"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "VALIDATED_CANDIDATE"
    assert candidate.executable_eligible is True
    assert "reclaim_rejection" in candidate.confluence_tags
    assert candidate.evidence["previous_spot_ltp"] == 22590.0


def test_vwap_reclaim_generates_put_candidate_after_confirmed_downside_reclaim():
    ctx = _base_context(
        spot_ltp=22580.0,
        vwap=22600.0,
        vwap_slope=-0.04,
        pe_premium_change=11.0,
        ce_premium_change=0.0,
        metadata={"previous_spot_ltp": 22612.0},
    )
    candidates = generate_vwap_reclaim_rejection_candidates(ctx, _regime(primary="TREND_DOWN", TREND_DOWN=0.6, CHOP=0.1))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "VALIDATED_CANDIDATE"
    assert candidate.executable_eligible is True
    assert candidate.evidence["premium_change"] == 11.0


def test_vwap_reclaim_returns_empty_in_chop_or_without_confirmation():
    confirmed = _base_context(metadata={"previous_spot_ltp": 22590.0})
    assert generate_vwap_reclaim_rejection_candidates(confirmed, _regime(CHOP=0.8)) == ()

    no_confirmation = _base_context(metadata={"previous_spot_ltp": 22610.0})
    assert generate_vwap_reclaim_rejection_candidates(no_confirmation, _regime(TREND_UP=0.5)) == ()

    too_far = _base_context(spot_ltp=22850.0, metadata={"previous_spot_ltp": 22590.0})
    assert generate_vwap_reclaim_rejection_candidates(too_far, _regime(TREND_UP=0.5)) == ()


def test_vwap_reclaim_blocks_bad_quote_quality_but_keeps_candidate_visible():
    ctx = _base_context(
        metadata={"previous_spot_ltp": 22590.0},
        fallback_used=True,
        quote_source="recovered_fallback",
        ce_premium_change=0.0,
        ce_spread_pct=9.0,
        option_ltp_age_sec=6.0,
    )
    candidates = generate_vwap_reclaim_rejection_candidates(ctx, _regime(TREND_UP=0.6, CHOP=0.1))
    pool = build_candidate_pool(candidates)
    summary = pool.summary()

    assert summary.total_count == 1
    assert summary.blocked_count == 1
    assert summary.executable_eligible_count == 0
    assert set(candidates[0].blockers) >= {
        "FALLBACK_QUOTE_ONLY",
        "OPTION_CONFIRMATION_MISSING",
        "WIDE_SPREAD",
        "STALE_OPTION_LTP",
    }


def test_failed_breakout_trap_generates_put_candidate_after_bull_trap_reentry():
    ctx = _base_context(
        spot_ltp=22645.0,
        orb_high=22660.0,
        day_high=22690.0,
        ce_premium_change=0.0,
        pe_premium_change=12.0,
        metadata={"previous_break_high": 22685.0, "price_reentered_range": True},
    )
    candidates = generate_failed_breakout_trap_candidates(ctx, _regime(primary="TRAP_RISK", TRAP_RISK=0.75))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == "failed_breakout_trap_v1"
    assert candidate.movement_type == "FAILED_BREAKOUT_TRAP"
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "VALIDATED_CANDIDATE"
    assert candidate.executable_eligible is True
    assert "suppress_weak_breakout_followthrough" in candidate.suppression_tags
    assert candidate.evidence["trap_type"] == "failed_upside_breakout_reentry"


def test_failed_breakout_trap_generates_call_candidate_after_bear_trap_reentry():
    ctx = _base_context(
        spot_ltp=22505.0,
        orb_low=22490.0,
        day_low=22460.0,
        ce_premium_change=12.0,
        pe_premium_change=0.0,
        metadata={"previous_break_low": 22470.0, "price_reentered_range": True},
    )
    candidates = generate_failed_breakout_trap_candidates(ctx, _regime(primary="TRAP_RISK", TRAP_RISK=0.75))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "VALIDATED_CANDIDATE"
    assert candidate.executable_eligible is True
    assert candidate.evidence["trap_type"] == "failed_downside_breakdown_reentry"


def test_failed_breakout_trap_returns_empty_without_reentry_evidence_or_when_too_far():
    no_reentry = _base_context(spot_ltp=22645.0, orb_high=22660.0, metadata={})
    assert generate_failed_breakout_trap_candidates(no_reentry, _regime(TRAP_RISK=0.8)) == ()

    too_far = _base_context(
        spot_ltp=22450.0,
        orb_high=22660.0,
        metadata={"previous_break_high": 22685.0, "price_reentered_range": True},
    )
    assert generate_failed_breakout_trap_candidates(too_far, _regime(TRAP_RISK=0.8)) == ()

    missing_core = _base_context(spot_ltp=None)
    assert generate_failed_breakout_trap_candidates(missing_core, _regime(TRAP_RISK=0.8)) == ()


def test_failed_breakout_trap_blocks_poor_quote_quality_but_keeps_trap_candidate_visible():
    ctx = _base_context(
        spot_ltp=22645.0,
        orb_high=22660.0,
        ce_premium_change=0.0,
        pe_premium_change=0.0,
        pe_spread_pct=8.0,
        option_ltp_age_sec=8.0,
        fallback_used=True,
        quote_source="recovered_fallback",
        metadata={"previous_break_high": 22685.0, "price_reentered_range": True},
    )
    candidates = generate_failed_breakout_trap_candidates(ctx, _regime(primary="TRAP_RISK", TRAP_RISK=0.8))
    pool = build_candidate_pool(candidates)
    summary = pool.summary()

    assert summary.total_count == 1
    assert summary.blocked_count == 1
    assert summary.hard_blocked_count == 1
    assert summary.executable_eligible_count == 0
    assert set(candidates[0].blockers) >= {
        "FALLBACK_QUOTE_ONLY",
        "OPTION_CONFIRMATION_MISSING",
        "WIDE_SPREAD",
        "STALE_OPTION_LTP",
    }
