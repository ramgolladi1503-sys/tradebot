from core.candidate_pool import build_candidate_pool
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates


def _regime(primary="COMPRESSION", **scores):
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
        "spot_ltp": 22650.0,
        "open_price": 22500.0,
        "vwap": 22600.0,
        "day_high": 22620.0,
        "day_low": 22480.0,
        "orb_high": 22610.0,
        "orb_low": 22490.0,
        "nearest_resistance": 22620.0,
        "nearest_support": 22490.0,
        "range_width_pct": 0.14,
        "atr_short": 35.0,
        "atr_long": 100.0,
        "volume_z": 1.5,
        "option_ce_ltp": 125.0,
        "option_pe_ltp": 92.0,
        "ce_premium_change": 13.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 55,
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def test_compression_breakout_generates_call_candidate_after_compression_release():
    ctx = _base_context()
    candidates = generate_compression_breakout_candidates(
        ctx,
        _regime(COMPRESSION=0.82, VOLATILITY_EXPANSION=0.45, TREND_UP=0.35),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == "compression_breakout_v1"
    assert candidate.movement_type == "COMPRESSION_BREAKOUT"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.blockers == ()
    assert "compression" in candidate.confluence_tags
    assert candidate.evidence["compression_score"] >= 0.5
    assert candidate.evidence["breakout_distance_pct"] > 0


def test_compression_breakout_generates_put_candidate_after_compression_breakdown():
    ctx = _base_context(
        spot_ltp=22450.0,
        vwap=22520.0,
        nearest_support=22480.0,
        nearest_resistance=22620.0,
        pe_premium_change=14.0,
        ce_premium_change=0.0,
    )
    candidates = generate_compression_breakout_candidates(
        ctx,
        _regime(COMPRESSION=0.82, VOLATILITY_EXPANSION=0.45, TREND_DOWN=0.35),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.evidence["premium_change"] == 14.0


def test_compression_breakout_returns_empty_without_real_compression_or_breakout():
    no_compression = _base_context(range_width_pct=0.8, atr_short=100.0, atr_long=100.0)
    assert generate_compression_breakout_candidates(no_compression, _regime(COMPRESSION=0.1)) == ()

    no_breakout = _base_context(spot_ltp=22619.0, nearest_resistance=22620.0)
    assert generate_compression_breakout_candidates(no_breakout, _regime(COMPRESSION=0.8)) == ()

    missing_core = _base_context(vwap=None)
    assert generate_compression_breakout_candidates(missing_core, _regime(COMPRESSION=0.8)) == ()


def test_compression_breakout_blocks_bad_quote_quality_but_keeps_candidate_visible():
    ctx = _base_context(
        fallback_used=True,
        quote_source="recovered_fallback",
        ce_spread_pct=9.0,
        ce_depth=None,
        option_ltp_age_sec=8.0,
    )
    candidates = generate_compression_breakout_candidates(ctx, _regime(COMPRESSION=0.8, TREND_UP=0.3))
    pool = build_candidate_pool(candidates)
    summary = pool.summary()

    assert summary.total_count == 1
    assert summary.raw_count == 1
    assert summary.blocked_count == 0
    assert summary.executable_eligible_count == 0
    assert candidates[0].blockers == ()


def test_trend_pullback_generates_call_candidate_when_uptrend_pullback_holds():
    ctx = _base_context(
        spot_ltp=22625.0,
        vwap=22600.0,
        nearest_support=22610.0,
        ce_premium_change=11.0,
        minutes_since_open=75,
    )
    candidates = generate_trend_pullback_candidates(ctx, _regime(primary="TREND_UP", TREND_UP=0.72))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == "trend_pullback_v1"
    assert candidate.movement_type == "TREND_PULLBACK"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert "pullback_hold" in candidate.confluence_tags
    assert candidate.evidence["trend_score"] == 0.72


def test_trend_pullback_generates_put_candidate_when_downtrend_pullback_rejects():
    ctx = _base_context(
        spot_ltp=22495.0,
        vwap=22520.0,
        nearest_resistance=22510.0,
        pe_premium_change=12.0,
        ce_premium_change=0.0,
        minutes_since_open=80,
    )
    candidates = generate_trend_pullback_candidates(ctx, _regime(primary="TREND_DOWN", TREND_DOWN=0.74))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.evidence["premium_change"] == 12.0


def test_trend_pullback_returns_empty_without_trend_or_when_chasing_late_move():
    weak_trend = _base_context(spot_ltp=22625.0, nearest_support=22610.0)
    assert generate_trend_pullback_candidates(weak_trend, _regime(primary="RANGE", TREND_UP=0.2)) == ()

    late_chase = _base_context(spot_ltp=22850.0, vwap=22600.0, nearest_support=22610.0)
    assert generate_trend_pullback_candidates(late_chase, _regime(primary="TREND_UP", TREND_UP=0.8)) == ()

    missing_core = _base_context(spot_ltp=None)
    assert generate_trend_pullback_candidates(missing_core, _regime(primary="TREND_UP", TREND_UP=0.8)) == ()


def test_trend_pullback_blocks_stale_fallback_wide_spread_candidate():
    ctx = _base_context(
        spot_ltp=22625.0,
        vwap=22600.0,
        nearest_support=22610.0,
        fallback_used=True,
        quote_source="recovered_fallback",
        ce_premium_change=0.0,
        ce_spread_pct=8.5,
        option_ltp_age_sec=7.0,
    )
    candidates = generate_trend_pullback_candidates(ctx, _regime(primary="TREND_UP", TREND_UP=0.75))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.blockers == ()
