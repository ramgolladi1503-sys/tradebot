"""Unit tests for Sentinel Live Stream Advisor NIFTY Dynamic Frictional Hurdle.

Proves:
1. Invariant: NIFTY trades with ATR < min_nifty_frictional_hurdle_atr are suppressed.
2. Invariant: Target points failing to clear min_nifty_hurdle_ratio * friction are suppressed.
3. Invariant: Percentage volatility sanity floor prevents starvation when spot moves.
4. Non-NIFTY bypass: BANKNIFTY and SENSEX bypass the NIFTY frictional hurdle.
5. Integration: Depth tick processing triggers VETO_NIFTY_FRICTIONAL_HURDLE appropriately.
6. Safety invariants: read_only=True, is_order_action=False, broker_api_called=False.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor
from core.upstox_stream_broadcaster import UpstoxLevel5DepthRecord


@pytest.fixture
def adapter():
    return InMemorySentinelAdapter(skew_threshold_ms=250.0, staleness_timeout_ms=1000.0)


@pytest.fixture
def advisor(adapter):
    return SentinelLiveStreamAdvisor(
        adapter=adapter,
        min_nifty_frictional_hurdle_atr=12.0,
        min_nifty_hurdle_ratio=2.0,
        enable_stdout=False,
    )


def test_safety_invariants(advisor):
    """Test required TradeBot safety invariants."""
    assert advisor.read_only is True
    assert advisor.is_order_action is False
    assert advisor.broker_api_called is False
    assert advisor.allowed_for_live_execution is False


def test_non_nifty_bypass(advisor):
    """Proves BANKNIFTY and SENSEX bypass NIFTY frictional hurdle."""
    ok_bn, reason_bn = advisor.evaluate_nifty_frictional_hurdle(
        index_name="BANKNIFTY",
        atr_15m=5.0,  # low ATR
        friction_drag_pts=10.0,
        target_pts=5.0,
    )
    assert ok_bn is True
    assert "NON_NIFTY_INDEX_BANKNIFTY_BYPASS" in reason_bn

    ok_sx, reason_sx = advisor.evaluate_nifty_frictional_hurdle(
        index_name="SENSEX",
        atr_15m=5.0,
        friction_drag_pts=15.0,
        target_pts=10.0,
    )
    assert ok_sx is True
    assert "NON_NIFTY_INDEX_SENSEX_BYPASS" in reason_sx


def test_nifty_insufficient_atr_veto(advisor):
    """Attacker 1 & Reviewer 1: Low ATR (< 12.0) must be rejected fail-closed."""
    ok, reason = advisor.evaluate_nifty_frictional_hurdle(
        index_name="NIFTY",
        atr_15m=10.5,
        friction_drag_pts=2.0,
        target_pts=15.0,
        spot_price=22500.0,
    )
    assert ok is False
    assert "NIFTY_INSUFFICIENT_VOLATILITY" in reason
    assert "10.5 < hurdle 12.0" in reason


def test_nifty_uneconomic_friction_drag_veto(advisor):
    """Attacker 2 & Reviewer 2: Target pts < 2.0x friction must be rejected."""
    # Here friction is 8.0 pts (e.g. wide spread), hurdle_req = 16.0 pts, target is only 15.0 pts
    ok, reason = advisor.evaluate_nifty_frictional_hurdle(
        index_name="NIFTY",
        atr_15m=14.0,  # ATR is fine
        friction_drag_pts=8.0,
        target_pts=15.0,
        spot_price=22500.0,
    )
    assert ok is False
    assert "NIFTY_FRICTION_DRAG_UNECONOMIC" in reason
    assert "Target 15.0pts < 2.0x friction" in reason


def test_nifty_percentage_volatility_fallacy_guard(advisor):
    """Attacker 3 & Reviewer 3: Normalizes for index price level changes."""
    # If NIFTY spot hypothetically reaches 40,000, 12 pts is only 0.03% (< 0.05%)
    ok, reason = advisor.evaluate_nifty_frictional_hurdle(
        index_name="NIFTY",
        atr_15m=14.0,
        friction_drag_pts=2.0,
        target_pts=15.0,
        spot_price=35000.0,  # 14 / 35000 = 0.04% < 0.05%
    )
    assert ok is False
    assert "NIFTY_PCT_VOLATILITY_STARVATION" in reason


def test_nifty_frictional_hurdle_pass_clean(advisor):
    """Proves valid economic setup clears hurdle."""
    ok, reason = advisor.evaluate_nifty_frictional_hurdle(
        index_name="NIFTY",
        atr_15m=14.0,
        friction_drag_pts=2.1,
        target_pts=15.0,
        spot_price=22500.0,  # 14 / 22500 = 0.062% >= 0.05%
    )
    assert ok is True
    assert "NIFTY_FRICTIONAL_HURDLE_CLEARED" in reason


def test_end_to_end_veto_nifty_frictional_hurdle_in_depth_tick(advisor):
    """Proves integration of VETO_NIFTY_FRICTIONAL_HURDLE in advisor alert pipeline."""
    from datetime import datetime, time as dt_time
    from core.upstox_stream_broadcaster import UpstoxStreamBroadcaster, UpstoxLevel5DepthRecord

    # Configure advisor to require higher ATR hurdle (e.g. 18.0) and allow immediate execution
    advisor.min_nifty_frictional_hurdle_atr = 18.0
    advisor.trade_lock_active = False
    advisor.market_open_time = dt_time(0, 0)
    advisor.opening_shock_end_time = dt_time(0, 0)
    advisor.eod_entry_freeze_time = dt_time(23, 59)

    now_ms = int(datetime.now().timestamp() * 1000)

    # Establish NIFTY spot tick above Opening Range High (22550.0) with moderate displacement (< 2.5 * ATR60)
    advisor.or_bounds["NIFTY"] = {"high": 22550.0, "low": 22450.0}
    advisor.spots["NIFTY"] = 22560.0
    advisor.spots_ts_ms["NIFTY"] = now_ms

    depth = UpstoxLevel5DepthRecord(
        token="NSE_FO|NIFTY26OCT22550CE",
        symbol="NIFTY 22550 CE",
        exchange_timestamp_ms=now_ms + 10,
        ingress_monotonic_ns=0,
        ingress_wall_utc="",
        sequence_id=1,
        ltp=100.0,
        volume=500000,
        open_interest=5000000,
        bid_p1=99.9, bid_q1=1000, bid_o1=5,
        bid_p2=99.8, bid_q2=1000, bid_o2=5,
        bid_p3=99.7, bid_q3=1000, bid_o3=5,
        bid_p4=99.6, bid_q4=1000, bid_o4=5,
        bid_p5=99.5, bid_q5=1000, bid_o5=5,
        ask_p1=100.1, ask_q1=1000, ask_o1=5,
        ask_p2=100.2, ask_q2=1000, ask_o2=5,
        ask_p3=100.3, ask_q3=1000, ask_o3=5,
        ask_p4=100.4, ask_q4=1000, ask_o4=5,
        ask_p5=100.5, ask_q5=1000, ask_o5=5,
    )

    advisor._evaluate_option_depth(depth)

    # History should contain alert with VETO_NIFTY_FRICTIONAL_HURDLE
    assert len(advisor.alerts_history) > 0
    latest = advisor.alerts_history[-1]
    assert latest.status_flag == "VETO_NIFTY_FRICTIONAL_HURDLE"
    assert "NIFTY_INSUFFICIENT_VOLATILITY" in latest.advisory
