from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.candidate_pool import build_candidate_pool
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.failed_breakout_trap import generate_failed_breakout_trap_candidates
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates
from tests.vwap_reclaim_test_support import EVALUATION_CUTOFF, bearish_history, bullish_history

IST = ZoneInfo("Asia/Kolkata")


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


def _trap_bar(offset, open_, high, low, close):
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST) + timedelta(minutes=offset)
    end = start + timedelta(minutes=1)
    return {
        "symbol": "NIFTY",
        "session_date": "2026-07-14",
        "timeframe": "1m",
        "bar_start_timestamp": start.isoformat(),
        "bar_end_timestamp": end.isoformat(),
        "timestamp": end.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1200.0,
        "source": "unit_test",
        "source_timestamp": end.isoformat(),
        "receipt_timestamp": (end + timedelta(seconds=1)).isoformat(),
        "is_complete": True,
    }


def _bull_trap_history():
    return [
        _trap_bar(0, 22640.0, 22655.0, 22630.0, 22650.0),
        _trap_bar(1, 22655.0, 22680.0, 22650.0, 22672.0),
        _trap_bar(2, 22670.0, 22675.0, 22635.0, 22645.0),
    ]


def _bear_trap_history():
    return [
        _trap_bar(0, 22505.0, 22520.0, 22495.0, 22500.0),
        _trap_bar(1, 22495.0, 22500.0, 22470.0, 22478.0),
        _trap_bar(2, 22480.0, 22510.0, 22475.0, 22505.0),
    ]


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
    candidate = candidates[0]
    assert candidate.direction == "BUY_CALL"
    assert candidate.evidence["temporal_evidence"]["vwap_provenance"] == "VWAP_AUTHORITATIVE"


def test_vwap_reclaim_generates_put_candidate_after_confirmed_downside_reclaim():
    ctx = _base_context(spot_ltp=22520.0, vwap=22540.0, vwap_slope=-0.04, pe_premium_change=11.0, ce_premium_change=0.0, completed_bar_history=bearish_history(), metadata={"previous_spot_ltp": 22585.0})
    candidates = generate_vwap_reclaim_rejection_candidates(ctx, _regime(primary="TREND_DOWN", TREND_DOWN=0.6, CHOP=0.1))
    assert candidates and candidates[0].direction == "BUY_PUT"


def test_vwap_reclaim_returns_empty_in_chop_or_without_confirmation():
    assert generate_vwap_reclaim_rejection_candidates(_base_context(), _regime(CHOP=0.8)) == ()
    assert generate_vwap_reclaim_rejection_candidates(_base_context(completed_bar_history=None, metadata={}), _regime(TREND_UP=0.5)) == ()
    assert generate_vwap_reclaim_rejection_candidates(_base_context(completed_bar_history=bullish_history()[:2]), _regime(TREND_UP=0.5)) == ()


def test_vwap_reclaim_blocks_bad_quote_quality_but_keeps_candidate_visible():
    ctx = _base_context(spot_ltp=22610.0, fallback_used=True, quote_source="recovered_fallback", ce_premium_change=0.0, ce_spread_pct=9.0, option_ltp_age_sec=6.0)
    candidates = generate_vwap_reclaim_rejection_candidates(ctx, _regime(TREND_UP=0.6, CHOP=0.1))
    summary = build_candidate_pool(candidates).summary()
    assert summary.total_count == 1 and summary.executable_eligible_count == 0


def test_failed_breakout_trap_generates_put_only_after_completed_bull_trap_reentry():
    ctx = _base_context(spot_ltp=22645.0, orb_high=22660.0, ce_premium_change=0.0, pe_premium_change=12.0, completed_bar_history=_bull_trap_history())
    candidates = generate_failed_breakout_trap_candidates(ctx, _regime(primary="TRAP_RISK", TRAP_RISK=0.75))
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.direction == "BUY_PUT"
    assert candidate.evidence["break_extreme"] >= 22680.0
    assert candidate.evidence["reentry_close"] < 22660.0
    assert candidate.evidence["reentry_index"] > candidate.evidence["break_index"]


def test_failed_breakout_trap_generates_call_only_after_completed_bear_trap_reentry():
    ctx = _base_context(spot_ltp=22505.0, orb_low=22490.0, nearest_support=22480.0, ce_premium_change=12.0, pe_premium_change=0.0, completed_bar_history=_bear_trap_history())
    candidates = generate_failed_breakout_trap_candidates(ctx, _regime(primary="TRAP_RISK", TRAP_RISK=0.75))
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.direction == "BUY_CALL"
    assert candidate.evidence["break_extreme"] <= 22470.0
    assert candidate.evidence["reentry_close"] > 22490.0
    assert candidate.evidence["reentry_index"] > candidate.evidence["break_index"]


def test_failed_breakout_metadata_alone_and_missing_option_evidence_cannot_trigger():
    metadata_only = _base_context(spot_ltp=22645.0, orb_high=22660.0, completed_bar_history=bullish_history(), metadata={"previous_break_high": 22685.0, "price_reentered_range": True}, ce_premium_change=0.0, pe_premium_change=12.0)
    assert generate_failed_breakout_trap_candidates(metadata_only, _regime(primary="TRAP_RISK", TRAP_RISK=0.8)) == ()
    missing_option = _base_context(spot_ltp=22645.0, orb_high=22660.0, completed_bar_history=_bull_trap_history(), ce_premium_change=None, pe_premium_change=12.0)
    assert generate_failed_breakout_trap_candidates(missing_option, _regime(primary="TRAP_RISK", TRAP_RISK=0.8)) == ()


def test_failed_breakout_trap_rejects_too_far_or_missing_core():
    too_far = _base_context(spot_ltp=22450.0, orb_high=22660.0, completed_bar_history=_bull_trap_history(), ce_premium_change=0.0, pe_premium_change=12.0)
    assert generate_failed_breakout_trap_candidates(too_far, _regime(TRAP_RISK=0.8)) == ()
    assert generate_failed_breakout_trap_candidates(_base_context(spot_ltp=None, completed_bar_history=_bull_trap_history()), _regime(TRAP_RISK=0.8)) == ()


def test_failed_breakout_trap_bad_quote_remains_non_executable_raw_candidate():
    ctx = _base_context(spot_ltp=22645.0, orb_high=22660.0, ce_premium_change=0.0, pe_premium_change=12.0, pe_spread_pct=8.0, option_ltp_age_sec=8.0, fallback_used=True, quote_source="recovered_fallback", completed_bar_history=_bull_trap_history())
    candidates = generate_failed_breakout_trap_candidates(ctx, _regime(primary="TRAP_RISK", TRAP_RISK=0.8))
    summary = build_candidate_pool(candidates).summary()
    assert summary.total_count == 1 and summary.executable_eligible_count == 0
