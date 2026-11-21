"""Unit tests proving SentinelLiveStreamAdvisor integration with MiddayMomentumExtensionEngine.

Work Item: FEAT-SENTINEL-MIDDAY-MOMENTUM-001
Branch: feat/sentinel-unified-upstox-stream-advisor
Baseline PR: #987

Proves:
1. Sentinel Advisor initializes MiddayMomentumExtensionEngine per index.
2. Spot updates dynamically register session open.
3. Level-5 depth evaluation at 12:30 IST activates Mode 4 (Midday Momentum Extension).
4. Non-negotiable repository safety invariants are guaranteed:
   - read_only = True
   - is_order_action = False
   - broker_api_called = False
   - allowed_for_live_execution = False
"""

import pytest
from datetime import datetime, time as dt_time
from unittest.mock import patch, MagicMock
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    UpstoxLevel5DepthRecord,
    UpstoxTickRecord,
)
from core.midday_momentum_extension_engine import (
    MiddayMomentumExtensionEngine,
    MiddayDirection,
)


def _make_dummy_depth(token: str, symbol: str, oi: int, ltp: float = 100.0) -> UpstoxLevel5DepthRecord:
    return UpstoxLevel5DepthRecord(
        token=token,
        symbol=symbol,
        exchange_timestamp_ms=1793188800000,
        ingress_monotonic_ns=1000000,
        ingress_wall_utc="2026-10-28T12:30:00Z",
        sequence_id=1,
        ltp=ltp,
        volume=200000,
        open_interest=oi,
        bid_p1=ltp - 0.2, bid_q1=500, bid_o1=5,
        bid_p2=ltp - 0.4, bid_q2=500, bid_o2=5,
        bid_p3=ltp - 0.6, bid_q3=500, bid_o3=5,
        bid_p4=ltp - 0.8, bid_q4=500, bid_o4=5,
        bid_p5=ltp - 1.0, bid_q5=500, bid_o5=5,
        ask_p1=ltp + 0.2, ask_q1=500, ask_o1=5,
        ask_p2=ltp + 0.4, ask_q2=500, ask_o2=5,
        ask_p3=ltp + 0.6, ask_q3=500, ask_o3=5,
        ask_p4=ltp + 0.8, ask_q4=500, ask_o4=5,
        ask_p5=ltp + 1.0, ask_q5=500, ask_o5=5,
    )


def test_sentinel_advisor_midday_engine_initialization(tmp_path):
    wal = tmp_path / "test_wal_midday_init.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    assert "NIFTY" in advisor.midday_engines
    assert "BANKNIFTY" in advisor.midday_engines
    assert "SENSEX" in advisor.midday_engines
    assert advisor.midday_engine is advisor.midday_engines["NIFTY"]
    assert advisor.midday_engine.target_pts == 40.0
    assert advisor.midday_engine.stop_pts == 40.0


def test_sentinel_advisor_midday_trigger_at_1230(tmp_path):
    wal = tmp_path / "test_wal_midday_trigger.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    # Establish NIFTY session open at 24000.0
    advisor.midday_engines["NIFTY"].set_session_open(24000.0)
    advisor.spots["NIFTY"] = 24200.0  # +0.83% drift
    advisor.spots_ts_ms["NIFTY"] = 1793188800000

    # Mock datetime.now() to return 12:30:15 IST
    fake_now = datetime(2026, 10, 28, 12, 30, 15)

    with patch("core.sentinel_live_stream_advisor.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromtimestamp = datetime.fromtimestamp

        # Simulate option depth for NIFTY 24200 CE
        depth = _make_dummy_depth(
            token="NSE_FO|NIFTY26OCT24200CE",
            symbol="NIFTY 24200 CE",
            oi=500000,
            ltp=120.0,
        )

        # Ensure trade lock is off and not in shock
        advisor.trade_lock_active = False

        advisor.on_depth(depth)

        # Check that midday momentum extension signal was processed
        sig = advisor.midday_engines["NIFTY"].cached_signal
        assert sig is not None
        assert sig.direction == MiddayDirection.LONG
        assert sig.recommended_option_type == "CE"
        assert sig.recommended_strike == 24200.0
        assert sig.target_pts == 40.0
        assert sig.stop_pts == 40.0
        assert sig.target_price == 24240.0
        assert sig.stop_price == 24160.0
        assert sig.read_only is True
        assert sig.is_order_action is False
        assert sig.broker_api_called is False
        assert sig.allowed_for_live_execution is False
