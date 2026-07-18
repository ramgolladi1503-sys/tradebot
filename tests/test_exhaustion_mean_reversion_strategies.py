from core.candidate_pool import build_candidate_pool
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.exhaustion_reversal import generate_exhaustion_reversal_candidates
from strategies.movement.mean_reversion_extension import generate_mean_reversion_extension_candidates


def _regime(primary="EXHAUSTION_RISK", **scores):
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
        "spot_ltp": 22740.0,
        "open_price": 22500.0,
        "vwap": 22580.0,
        "vwap_slope": 0.01,
        "day_high": 22760.0,
        "day_low": 22480.0,
        "nearest_resistance": 22760.0,
        "nearest_support": 22490.0,
        "range_width_pct": 0.50,
        "atr_short": 80.0,
        "atr_long": 100.0,
        "volume_z": 0.35,
        "option_ce_ltp": 125.0,
        "option_pe_ltp": 92.0,
        "ce_premium_change": 0.0,
        "pe_premium_change": 10.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 110,
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def test_exhaustion_reversal_generates_put_candidate_after_upside_stall():
    ctx = _base_context()
    candidates = generate_exhaustion_reversal_candidates(
        ctx,
        _regime(EXHAUSTION_RISK=0.75, TREND_UP=0.35),
    )

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.strategy_id == "exhaustion_reversal_v1"
    assert candidate.movement_type == "EXHAUSTION_REVERSAL"
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert "exhaustion" in candidate.confluence_tags
    assert candidate.evidence["exhaustion_type"] == "upside_exhaustion"


def test_exhaustion_reversal_generates_call_candidate_after_downside_stall():
    ctx = _base_context(
        spot_ltp=22420.0,
        vwap=22580.0,
        ce_premium_change=11.0,
        pe_premium_change=0.0,
    )
    candidates = generate_exhaustion_reversal_candidates(
        ctx,
        _regime(EXHAUSTION_RISK=0.75, TREND_DOWN=0.35),
    )

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.evidence["exhaustion_type"] == "downside_exhaustion"


def test_exhaustion_reversal_rejects_non_stretched_and_strong_continuation():
    not_stretched = _base_context(spot_ltp=22610.0, vwap=22580.0)
    assert generate_exhaustion_reversal_candidates(not_stretched, _regime(EXHAUSTION_RISK=0.8)) == ()

    strong_continuation = _base_context(ce_premium_change=22.0, volume_z=3.0, pe_premium_change=0.0)
    assert generate_exhaustion_reversal_candidates(strong_continuation, _regime(EXHAUSTION_RISK=0.8)) == ()

    missing_core = _base_context(vwap=None)
    assert generate_exhaustion_reversal_candidates(missing_core, _regime(EXHAUSTION_RISK=0.8)) == ()


def test_exhaustion_reversal_blocks_bad_quote_quality_but_keeps_candidate_visible():
    ctx = _base_context(
        fallback_used=True,
        quote_source="recovered_fallback",
        pe_premium_change=0.0,
        pe_spread_pct=8.0,
        option_ltp_age_sec=8.0,
    )
    candidates = generate_exhaustion_reversal_candidates(ctx, _regime(EXHAUSTION_RISK=0.8))
    pool = build_candidate_pool(candidates)
    summary = pool.summary()

    assert summary.total_count == 1
    assert summary.raw_count == 1
    assert summary.blocked_count == 0
    assert summary.executable_eligible_count == 0
    assert candidates[0].blockers == ()


def test_mean_reversion_extension_generates_put_candidate_from_upper_range_extension():
    ctx = _base_context(
        spot_ltp=22710.0,
        vwap=22580.0,
        nearest_resistance=22720.0,
        pe_premium_change=10.0,
        ce_premium_change=0.0,
    )
    candidates = generate_mean_reversion_extension_candidates(
        ctx,
        _regime(primary="RANGE", RANGE=0.72, TREND_UP=0.15, VOLATILITY_EXPANSION=0.05),
    )

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.strategy_id == "mean_reversion_extension_v1"
    assert candidate.movement_type == "MEAN_REVERSION_EXTENSION"
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.evidence["reversion_type"] == "upper_extension_reversion"


def test_mean_reversion_extension_generates_call_candidate_from_lower_range_extension():
    ctx = _base_context(
        spot_ltp=22460.0,
        vwap=22580.0,
        nearest_support=22450.0,
        ce_premium_change=10.0,
        pe_premium_change=0.0,
    )
    candidates = generate_mean_reversion_extension_candidates(
        ctx,
        _regime(primary="RANGE", RANGE=0.72, TREND_DOWN=0.15, VOLATILITY_EXPANSION=0.05),
    )

    assert candidates
    assert candidates[1:] == ()
    candidate = candidates[0]
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.evidence["reversion_type"] == "lower_extension_reversion"


def test_mean_reversion_rejects_non_range_and_strong_continuation():
    non_range = _base_context(spot_ltp=22710.0, vwap=22580.0)
    assert generate_mean_reversion_extension_candidates(non_range, _regime(primary="TREND_UP", TREND_UP=0.75)) == ()

    strong_continuation = _base_context(
        spot_ltp=22710.0,
        vwap=22580.0,
        nearest_resistance=22720.0,
        ce_premium_change=22.0,
        pe_premium_change=0.0,
        volume_z=3.0,
    )
    assert generate_mean_reversion_extension_candidates(
        strong_continuation,
        _regime(primary="RANGE", RANGE=0.7, TREND_UP=0.75, VOLATILITY_EXPANSION=0.7),
    ) == ()

    missing_core = _base_context(spot_ltp=None)
    assert generate_mean_reversion_extension_candidates(missing_core, _regime(primary="RANGE", RANGE=0.8)) == ()


def test_mean_reversion_blocks_bad_quote_quality_but_keeps_candidate_visible():
    ctx = _base_context(
        spot_ltp=22710.0,
        vwap=22580.0,
        nearest_resistance=22720.0,
        fallback_used=True,
        quote_source="recovered_fallback",
        pe_premium_change=0.0,
        pe_spread_pct=9.0,
        option_ltp_age_sec=8.0,
    )
    candidates = generate_mean_reversion_extension_candidates(ctx, _regime(primary="RANGE", RANGE=0.8))
    pool = build_candidate_pool(candidates)
    summary = pool.summary()

    assert summary.total_count == 1
    assert summary.raw_count == 1
    assert summary.blocked_count == 0
    assert summary.hard_blocked_count == 0
    assert summary.executable_eligible_count == 0
    assert candidates[0].blockers == ()
