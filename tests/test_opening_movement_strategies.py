from core.candidate_pool import build_candidate_pool
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
import pytest
from strategies.movement.opening_drive import generate_opening_drive_candidates
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from tests.test_opening_range_retest_temporal_fixture_contract import (
    CALL_VALID_ROWS,
    OPENING_RANGE_ROWS,
    PUT_VALID_ROWS,
    _history_state_for_rows,
    _temporal_context,
)


def _regime(**scores):
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
    return MovementRegimeResult(schema_version=1, primary_regime="TREND_UP", scores=base)


def _base_context(**overrides):
    payload = {
        "symbol": "NIFTY",
        "spot_ltp": 22620.0,
        "open_price": 22500.0,
        "vwap": 22540.0,
        "orb_high": 22600.0,
        "orb_low": 22460.0,
        "volume_z": 1.5,
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
        "ce_premium_change": 12.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 8,
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def test_opening_drive_generates_valid_call_candidate():
    ctx = _base_context()
    result = generate_opening_drive_candidates(ctx, _regime(TREND_UP=0.8, VOLATILITY_EXPANSION=0.4))

    assert result
    assert result[1:] == ()
    candidate = result[0]
    assert candidate.strategy_id == "opening_drive_v1"
    assert candidate.movement_type == "OPENING_DRIVE"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.blockers == ()
    assert "opening_drive" in candidate.confluence_tags
    assert candidate.evidence["premium_change"] == 12.0


def test_opening_drive_generates_valid_put_candidate():
    ctx = _base_context(
        spot_ltp=22380.0,
        open_price=22500.0,
        vwap=22450.0,
        pe_premium_change=14.0,
        ce_premium_change=0.0,
    )
    result = generate_opening_drive_candidates(ctx, _regime(TREND_DOWN=0.8, VOLATILITY_EXPANSION=0.4))

    assert result
    assert result[1:] == ()
    candidate = result[0]
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.evidence["premium_change"] == 14.0


def test_opening_drive_returns_empty_when_outside_opening_window_or_missing_core_data():
    assert generate_opening_drive_candidates(_base_context(minutes_since_open=30), _regime()) == ()
    assert generate_opening_drive_candidates(_base_context(open_price=None), _regime()) == ()


def test_opening_drive_blocks_fallback_stale_wide_spread_and_missing_depth():
    ctx = _base_context(
        fallback_used=True,
        quote_source="recovered_fallback",
        ce_spread_pct=8.5,
        ce_depth=None,
        option_ltp_age_sec=7.0,
    )
    result = generate_opening_drive_candidates(ctx, _regime(TREND_UP=0.8))

    assert result
    assert result[1:] == ()
    candidate = result[0]
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.blockers == ()


def test_orb_retest_generates_valid_call_candidate_near_retest_level():
    state = _history_state_for_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    ctx = _temporal_context(state, ce_premium_change=10.0)
    result = generate_opening_range_retest_candidates(
        ctx,
        _regime(TREND_UP=0.6, VOLATILITY_EXPANSION=0.3),
    )

    assert result
    assert result[1:] == ()
    candidate = result[0]
    assert candidate.strategy_id == "opening_range_retest_v1"
    assert candidate.movement_type == "OPENING_RANGE_RETEST"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert "orb_retest" in candidate.confluence_tags
    assert candidate.evidence["setup_identity"]["setup_id"]
    assert candidate.evidence["setup_identity"]["history_hash"]
    assert candidate.evidence["setup_identity"]["proposal_ready_at_iso"] == "2026-07-14T09:34:00+05:30"
    assert candidate.lineage["promotion_state"] == "READY_FOR_PUBLICATION"
    assert candidate.raw_score == pytest.approx(0.42150442477876104, abs=1e-6)


def test_orb_retest_generates_valid_put_candidate_near_retest_level():
    state = _history_state_for_rows(OPENING_RANGE_ROWS + PUT_VALID_ROWS[:4])
    ctx = _temporal_context(state, pe_premium_change=11.0, ce_premium_change=0.0)
    result = generate_opening_range_retest_candidates(
        ctx,
        _regime(TREND_DOWN=0.6, VOLATILITY_EXPANSION=0.3),
    )

    assert result
    assert result[1:] == ()
    candidate = result[0]
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.executable_eligible is False
    assert candidate.evidence["setup_identity"]["setup_id"]
    assert candidate.evidence["setup_identity"]["history_hash"]


def test_orb_retest_returns_empty_when_timing_or_retest_evidence_missing():
    assert generate_opening_range_retest_candidates(_base_context(minutes_since_open=8), _regime()) == ()
    assert generate_opening_range_retest_candidates(_base_context(orb_high=None), _regime()) == ()
    assert generate_opening_range_retest_candidates(
        _base_context(minutes_since_open=35, spot_ltp=22750.0, orb_high=22600.0),
        _regime(),
    ) == ()


def test_orb_retest_blocked_candidates_remain_visible_in_pool_summary():
    state = _history_state_for_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    ctx = _temporal_context(
        state,
        fallback_used=True,
        quote_source="recovered_fallback",
        ce_premium_change=0.0,
        ce_spread_pct=9.0,
        option_ltp_age_sec=5.0,
    )
    candidates = generate_opening_range_retest_candidates(ctx, _regime(TREND_UP=0.5))
    pool = build_candidate_pool(candidates)
    summary = pool.summary()

    assert summary.total_count == 1
    assert summary.raw_count == 1
    assert summary.blocked_count == 0
    assert summary.hard_blocked_count == 0
    assert summary.executable_eligible_count == 0
    assert candidates[0].blockers == ()
