from core.candidate_pool import build_candidate_pool
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.failed_breakout_trap import generate_failed_breakout_trap_candidates
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates
from tests.vwap_reclaim_test_support import EVALUATION_CUTOFF, _bar, bearish_history, bullish_history


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
        "ts_epoch": EVALUATION_CUTOFF,
        "open_price": 22500.0,
        "vwap": 22540.0,
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
        "completed_bar_history": bullish_history(),
        "metadata": {"previous_spot_ltp": 22495.0, "vwap_reclaim_up_confirmed": True},
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def test_vwap_reclaim_generates_call_candidate_after_confirmed_reclaim():
    ctx = _base_context(spot_ltp=22610.0, vwap=22540.0, vwap_slope=0.04)
    candidates = generate_vwap_reclaim_rejection_candidates(ctx, _regime(TREND_UP=0.6, CHOP=0.1))

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.strategy_id == "vwap_reclaim_rejection_v1"
    assert candidate.movement_type == "VWAP_RECLAIM_REJECTION"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.entry_trigger == "confirmed_vwap_reclaim_hold"
    assert candidate.rank_reason == "confirmed VWAP reclaim and hold in a non-chop regime"
    assert candidate.confluence_tags == ("vwap", "reclaim_hold")
    assert candidate.evidence["confirmation_type"] == "upside_vwap_reclaim_hold"
    assert candidate.evidence["implemented_pattern"] == "VWAP_RECLAIM_HOLD"
    assert candidate.evidence["compatibility_strategy_id"] == "vwap_reclaim_rejection_v1"
    assert "rejection" not in candidate.entry_trigger
    assert "rejection" not in candidate.rank_reason
    assert "rejection" not in candidate.evidence["confirmation_type"]
    assert candidate.evidence["previous_spot_ltp"] == 22495.0
    assert candidate.evidence["temporal_evidence"]["vwap_provenance"] == "VWAP_AUTHORITATIVE"
    assert candidate.evidence["temporal_evidence"]["sequence_bar_timestamps"] == (
        "2026-07-14T09:16:00+05:30",
        "2026-07-14T09:17:00+05:30",
        "2026-07-14T09:18:00+05:30",
    )


def test_vwap_reclaim_generates_put_candidate_after_confirmed_downside_reclaim():
    ctx = _base_context(
        spot_ltp=22520.0,
        vwap=22540.0,
        vwap_slope=-0.04,
        pe_premium_change=11.0,
        ce_premium_change=0.0,
        completed_bar_history=bearish_history(),
        metadata={"previous_spot_ltp": 22585.0, "vwap_reclaim_down_confirmed": True},
    )
    candidates = generate_vwap_reclaim_rejection_candidates(ctx, _regime(primary="TREND_DOWN", TREND_DOWN=0.6, CHOP=0.1))

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.entry_trigger == "confirmed_vwap_reclaim_hold"
    assert candidate.rank_reason == "confirmed VWAP reclaim and hold in a non-chop regime"
    assert candidate.confluence_tags == ("vwap", "reclaim_hold")
    assert candidate.evidence["confirmation_type"] == "downside_vwap_reclaim_hold"
    assert candidate.evidence["implemented_pattern"] == "VWAP_RECLAIM_HOLD"
    assert candidate.evidence["compatibility_strategy_id"] == "vwap_reclaim_rejection_v1"
    assert candidate.evidence["premium_change"] == 11.0
    assert candidate.evidence["temporal_evidence"]["vwap_provenance"] == "VWAP_AUTHORITATIVE"


def test_vwap_reclaim_hold_preserves_compatibility_identity_and_profile_values():
    ctx = _base_context(spot_ltp=22610.0, vwap=22540.0, vwap_slope=0.04)
    candidate = generate_vwap_reclaim_rejection_candidates(ctx, _regime(TREND_UP=0.6, CHOP=0.1))[0]

    assert candidate.strategy_id == "vwap_reclaim_rejection_v1"
    assert candidate.movement_type == "VWAP_RECLAIM_REJECTION"
    assert candidate.lineage["params_used"] == {
        "MIN_VWAP_DISTANCE_PCT": 0.00035,
        "MAX_VWAP_ENTRY_DISTANCE_PCT": 0.0035,
        "MAX_CHOP_SCORE": 0.55,
    }
    assert candidate.evidence["temporal_contract_version"] == "vwap_reclaim_causal_v1"


def test_vwap_reclaim_hold_does_not_emit_for_incomplete_or_same_side_sequences():
    below_below_above = [
        _bar(0, 22500.0, 22520.0, 22490.0, 22490.0),
        _bar(1, 22500.0, 22520.0, 22490.0, 22500.0),
        _bar(2, 22590.0, 22610.0, 22550.0, 22580.0),
    ]
    above_above_below = [
        _bar(0, 22580.0, 22590.0, 22565.0, 22585.0),
        _bar(1, 22575.0, 22590.0, 22560.0, 22580.0),
        _bar(2, 22500.0, 22510.0, 22490.0, 22500.0),
    ]
    same_side = [
        _bar(0, 22580.0, 22590.0, 22565.0, 22585.0),
        _bar(1, 22590.0, 22605.0, 22570.0, 22595.0),
        _bar(2, 22600.0, 22620.0, 22590.0, 22610.0),
    ]

    assert generate_vwap_reclaim_rejection_candidates(
        _base_context(completed_bar_history=below_below_above),
        _regime(TREND_UP=0.6, CHOP=0.1),
    ) == ()
    assert generate_vwap_reclaim_rejection_candidates(
        _base_context(spot_ltp=22520.0, completed_bar_history=above_above_below),
        _regime(primary="TREND_DOWN", TREND_DOWN=0.6, CHOP=0.1),
    ) == ()
    assert generate_vwap_reclaim_rejection_candidates(
        _base_context(completed_bar_history=same_side),
        _regime(TREND_UP=0.6, CHOP=0.1),
    ) == ()


def test_vwap_reclaim_hold_future_cutoff_and_vwap_mismatch_remain_fail_closed():
    baseline = generate_vwap_reclaim_rejection_candidates(
        _base_context(spot_ltp=22610.0, completed_bar_history=bullish_history()),
        _regime(TREND_UP=0.6, CHOP=0.1),
    )[0]
    with_future = generate_vwap_reclaim_rejection_candidates(
        _base_context(spot_ltp=22610.0, completed_bar_history=bullish_history(include_future=True)),
        _regime(TREND_UP=0.6, CHOP=0.1),
    )[0]
    mismatch = generate_vwap_reclaim_rejection_candidates(
        _base_context(vwap=22541.0),
        _regime(TREND_UP=0.6, CHOP=0.1),
    )

    assert baseline.raw_score == with_future.raw_score
    assert baseline.evidence["temporal_evidence"]["history_hash"] == with_future.evidence["temporal_evidence"]["history_hash"]
    assert baseline.evidence["temporal_evidence"]["sequence_closes"] == with_future.evidence["temporal_evidence"]["sequence_closes"]
    assert mismatch == ()


def test_vwap_reclaim_returns_empty_in_chop_or_without_confirmation():
    confirmed = _base_context()
    assert generate_vwap_reclaim_rejection_candidates(confirmed, _regime(CHOP=0.8)) == ()

    no_history = _base_context(completed_bar_history=None, metadata={})
    assert generate_vwap_reclaim_rejection_candidates(no_history, _regime(TREND_UP=0.5)) == ()

    incomplete_sequence = _base_context(
        completed_bar_history=bullish_history()[:2],
        metadata={"previous_spot_ltp": 22495.0},
    )
    assert generate_vwap_reclaim_rejection_candidates(incomplete_sequence, _regime(TREND_UP=0.5)) == ()

    too_far = _base_context(spot_ltp=22850.0, metadata={"previous_spot_ltp": 22495.0})
    assert generate_vwap_reclaim_rejection_candidates(too_far, _regime(TREND_UP=0.5)) == ()


def test_vwap_reclaim_blocks_bad_quote_quality_but_keeps_candidate_visible():
    ctx = _base_context(
        spot_ltp=22610.0,
        metadata={"previous_spot_ltp": 22495.0},
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
    assert summary.raw_count == 1
    assert summary.blocked_count == 0
    assert summary.executable_eligible_count == 0
    assert candidates[0].blockers == ()


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

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.strategy_id == "failed_breakout_trap_v1"
    assert candidate.movement_type == "FAILED_BREAKOUT_TRAP"
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
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

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
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
    assert summary.raw_count == 1
    assert summary.blocked_count == 0
    assert summary.hard_blocked_count == 0
    assert summary.executable_eligible_count == 0
    assert candidates[0].blockers == ()
