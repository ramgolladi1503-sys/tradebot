from core.candidate_pool import build_candidate_pool
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.event_volatility_expansion import generate_event_volatility_expansion_candidates
from strategies.movement.late_day_momentum import generate_late_day_momentum_candidates


def _regime(primary="VOLATILITY_EXPANSION", **scores):
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
        "spot_ltp": 22700.0,
        "open_price": 22500.0,
        "vwap": 22600.0,
        "vwap_slope": 0.04,
        "day_high": 22720.0,
        "day_low": 22480.0,
        "nearest_resistance": 22740.0,
        "nearest_support": 22580.0,
        "range_width_pct": 0.80,
        "atr_short": 150.0,
        "atr_long": 90.0,
        "volume_z": 2.2,
        "volatility_state": "EXPANDING",
        "option_ce_ltp": 135.0,
        "option_pe_ltp": 92.0,
        "ce_premium_change": 16.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.9,
        "pe_spread_pct": 0.9,
        "ce_depth": 1400.0,
        "pe_depth": 1400.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 260,
        "minutes_to_close": 70,
        "expiry_context": False,
        "metadata": {"event_state": "ACTIVE"},
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def test_event_volatility_generates_call_candidate_on_upside_expansion():
    ctx = _base_context()
    candidates = generate_event_volatility_expansion_candidates(
        ctx,
        _regime(VOLATILITY_EXPANSION=0.82, TREND_UP=0.55),
    )

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.strategy_id == "event_volatility_expansion_v1"
    assert candidate.movement_type == "EVENT_VOLATILITY_EXPANSION"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert "volatility_expansion" in candidate.confluence_tags
    assert candidate.evidence["atr_short_long_ratio"] > 1.15


def test_event_volatility_generates_put_candidate_on_downside_expansion():
    ctx = _base_context(
        spot_ltp=22480.0,
        vwap=22580.0,
        pe_premium_change=15.0,
        ce_premium_change=0.0,
    )
    candidates = generate_event_volatility_expansion_candidates(
        ctx,
        _regime(VOLATILITY_EXPANSION=0.82, TREND_DOWN=0.55),
    )

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.evidence["expansion_type"] == "downside_volatility_expansion"


def test_event_volatility_rejects_missing_data_low_expansion_and_late_spike_chase():
    missing_core = _base_context(vwap=None)
    assert generate_event_volatility_expansion_candidates(missing_core, _regime(VOLATILITY_EXPANSION=0.8)) == ()

    low_expansion = _base_context(atr_short=90.0, atr_long=100.0, volume_z=0.7, volatility_state="NORMAL")
    assert generate_event_volatility_expansion_candidates(low_expansion, _regime(VOLATILITY_EXPANSION=0.1)) == ()

    late_chase = _base_context(spot_ltp=23050.0, vwap=22600.0)
    assert generate_event_volatility_expansion_candidates(late_chase, _regime(VOLATILITY_EXPANSION=0.9)) == ()


def test_event_volatility_blocks_bad_quote_quality_but_keeps_candidate_visible():
    ctx = _base_context(
        fallback_used=True,
        quote_source="recovered_fallback",
        ce_premium_change=0.0,
        ce_spread_pct=8.0,
        option_ltp_age_sec=7.0,
    )
    candidates = generate_event_volatility_expansion_candidates(ctx, _regime(VOLATILITY_EXPANSION=0.85))
    pool = build_candidate_pool(candidates)
    summary = pool.summary()

    assert summary.total_count == 1
    assert summary.raw_count == 1
    assert summary.blocked_count == 0
    assert summary.executable_eligible_count == 0
    assert candidates[0].blockers == ()


def test_late_day_momentum_generates_call_candidate_after_afternoon_confirmation():
    ctx = _base_context()
    candidates = generate_late_day_momentum_candidates(
        ctx,
        _regime(primary="TREND_UP", TREND_UP=0.76, CHOP=0.1),
    )

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.strategy_id == "late_day_momentum_v1"
    assert candidate.movement_type == "LATE_DAY_MOMENTUM"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert "late_day" in candidate.confluence_tags


def test_late_day_momentum_generates_put_candidate_after_afternoon_downtrend():
    ctx = _base_context(
        spot_ltp=22480.0,
        vwap=22580.0,
        pe_premium_change=14.0,
        ce_premium_change=0.0,
    )
    candidates = generate_late_day_momentum_candidates(
        ctx,
        _regime(primary="TREND_DOWN", TREND_DOWN=0.76, CHOP=0.1),
    )

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.evidence["momentum_type"] == "late_day_downside_momentum"


def test_late_day_momentum_rejects_bad_timing_chop_and_chase_distance():
    too_early = _base_context(minutes_since_open=120)
    assert generate_late_day_momentum_candidates(too_early, _regime(primary="TREND_UP", TREND_UP=0.8)) == ()

    too_close = _base_context(minutes_to_close=10)
    assert generate_late_day_momentum_candidates(too_close, _regime(primary="TREND_UP", TREND_UP=0.8)) == ()

    choppy = _base_context()
    assert generate_late_day_momentum_candidates(choppy, _regime(primary="CHOP", TREND_UP=0.8, CHOP=0.8)) == ()

    chase = _base_context(spot_ltp=22950.0, vwap=22600.0)
    assert generate_late_day_momentum_candidates(chase, _regime(primary="TREND_UP", TREND_UP=0.8)) == ()


def test_late_day_momentum_marks_expiry_warning_and_blocks_bad_quote_quality():
    ctx = _base_context(
        expiry_context=True,
        fallback_used=True,
        quote_source="recovered_fallback",
        ce_premium_change=0.0,
        ce_spread_pct=9.0,
        option_ltp_age_sec=8.0,
    )
    candidates = generate_late_day_momentum_candidates(ctx, _regime(primary="TREND_UP", TREND_UP=0.8, CHOP=0.1))
    pool = build_candidate_pool(candidates)
    summary = pool.summary()

    assert summary.total_count == 1
    assert summary.raw_count == 1
    assert summary.blocked_count == 0
    assert summary.hard_blocked_count == 0
    assert summary.executable_eligible_count == 0
    assert "expiry_context_late_day" in candidates[0].warnings
    assert candidates[0].blockers == ()
