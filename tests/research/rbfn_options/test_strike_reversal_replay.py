"""Tests for Option Strike Reversal Execution Replay.

Verifies:
- Blue line reclaim trigger (prior close <= ref < current close)
- Causal fill at next bar open + half-spread + slippage
- Enforced R:R >= 2.0
- Conservative stop precedence (SL wins if SL and TP occur in same candle)
- Rejection on missing minute bars in holding window
- Full statutory costs (STT, GST, brokerage, exchange, SEBI, stamp duty)
"""
from __future__ import annotations

import pandas as pd
import pytest

from research.rbfn_options.core.strike_reversal_replay import (
    ReversalReplayEngine,
    StatutoryCosts,
    TrailingStopConfig,
)


def make_sample_bars(base_time="2026-05-07 09:15:00", num_bars=60) -> pd.DataFrame:
    timestamps = pd.date_range(base_time, periods=num_bars, freq="min")
    records = []
    price = 45.0
    for ts in timestamps:
        records.append({
            "timestamp": ts,
            "open": price,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
        })
    return pd.DataFrame(records)


def test_statutory_costs_computation():
    costs = StatutoryCosts(
        brokerage_per_order_inr=20.0,
        gst_rate=0.18,
        exchange_rate_on_turnover=0.0005,
        sebi_rate_on_turnover=0.000001,
        stamp_buy_rate=0.00003,
        stt_sell_rate=0.000625,
        half_spread_premium_points=0.25,
        slippage_premium_points_per_side=0.25,
    )
    costs.validate()

    fees = costs.compute_fees(buy_premium=50.0, sell_premium=70.0, lot_size=50)
    # Buy value: 2500, Sell value: 3500, Turnover: 6000
    # Brokerage: 40
    # Exchange: 6000 * 0.0005 = 3.0
    # SEBI: 6000 * 0.000001 = 0.006
    # GST: 0.18 * (40 + 3 + 0.006) = 7.74108
    # Stamp: 2500 * 0.00003 = 0.075
    # STT: 3500 * 0.000625 = 2.1875
    # Total ~ 40 + 3 + 0.006 + 7.74108 + 0.075 + 2.1875 = 53.00958
    assert 52.0 < fees < 54.0


def test_rr_ratio_enforcement():
    engine = ReversalReplayEngine()
    df = make_sample_bars()
    # R:R = 15 / 10 = 1.5 < 2.0 -> Must raise ValueError
    with pytest.raises(ValueError, match="R:R requirement violated"):
        engine.replay_session(
            bars_df=df,
            reference_level=48.0,
            date="2026-05-07",
            expiry="2026-05-07",
            strike=22500.0,
            option_type="CE",
            stop_points=10.0,
            target_points=15.0,  # 1.5 R:R
        )


def test_successful_reversal_take_profit():
    bars = make_sample_bars("2026-05-07 09:15:00", 40)
    # 09:15 is idx 0
    # 09:20 is idx 5 (close = 45.0 <= 48.0)
    # 09:21 is idx 6 -> let's make it cross above 48.0 (close = 49.0)
    bars.loc[5, 'close'] = 45.0
    bars.loc[6, 'open'] = 45.5
    bars.loc[6, 'close'] = 49.0  # Blue Line Reclaim!

    # 09:22 is idx 7 -> Entry bar (open = 50.0). Entry fill = 50.0 + 0.5 = 50.5
    bars.loc[7, 'open'] = 50.0
    bars.loc[7, 'high'] = 52.0
    bars.loc[7, 'low'] = 49.5
    bars.loc[7, 'close'] = 51.0

    # Target: 20 pts -> target_price = 70.5
    # At 09:25 (idx 10), spike high to 72.0
    bars.loc[10, 'high'] = 72.0

    engine = ReversalReplayEngine()
    res = engine.replay_session(
        bars_df=bars,
        reference_level=48.0,
        date="2026-05-07",
        expiry="2026-05-07",
        strike=22500.0,
        option_type="CE",
        stop_points=10.0,
        target_points=20.0,
        lot_size=50,
    )

    assert res.status == 'TRADE'
    trade = res.trade
    assert trade is not None
    assert trade.exit_reason == 'TP'
    assert trade.entry_price == 50.5
    assert trade.target_price == 70.5
    assert trade.exit_price == 70.0  # 70.5 - 0.5 exit slippage/spread
    assert trade.gross_pnl_points == round(70.0 - 50.5, 2)
    assert trade.reward_risk_ratio == 2.0
    assert trade.net_pnl_inr > 0


def test_conservative_stop_precedence():
    bars = make_sample_bars("2026-05-07 09:15:00", 40)
    bars.loc[5, 'close'] = 45.0
    bars.loc[6, 'close'] = 49.0  # Signal at 09:21

    # Entry at 09:22 (idx 7) open=50.0 -> entry_fill=50.5. Stop=40.5, Target=70.5
    bars.loc[7, 'open'] = 50.0

    # At 09:23 (idx 8), both SL and TP are touched!
    # Low = 39.0 (< 40.5), High = 75.0 (> 70.5)
    bars.loc[8, 'low'] = 39.0
    bars.loc[8, 'high'] = 75.0

    engine = ReversalReplayEngine()
    res = engine.replay_session(
        bars_df=bars,
        reference_level=48.0,
        date="2026-05-07",
        expiry="2026-05-07",
        strike=22500.0,
        option_type="CE",
        stop_points=10.0,
        target_points=20.0,
    )

    assert res.status == 'TRADE'
    assert res.trade.exit_reason == 'SL'  # Conservative stop precedence!


def test_missing_minute_during_holding_rejected():
    bars = make_sample_bars("2026-05-07 09:15:00", 30)
    bars.loc[5, 'close'] = 45.0
    bars.loc[6, 'close'] = 49.0  # Signal

    # Remove candle idx 10 (creating a time gap)
    bars_gapped = bars.drop(index=[10]).reset_index(drop=True)

    engine = ReversalReplayEngine()
    res = engine.replay_session(
        bars_df=bars_gapped,
        reference_level=48.0,
        date="2026-05-07",
        expiry="2026-05-07",
        strike=22500.0,
        option_type="CE",
        stop_points=10.0,
        target_points=20.0,
    )

    assert res.status == 'REJECT'
    assert 'missing minute candle during trade holding' in res.reason


def test_trailing_stop_breakeven_activation():
    bars = make_sample_bars("2026-05-07 09:15:00", 40)
    bars.loc[5, 'close'] = 45.0
    bars.loc[6, 'close'] = 49.0  # Signal at 09:21 (idx 6)

    # Entry at 09:22 (idx 7) open=50.0 -> entry_fill=50.5. Initial stop=40.5, Target=70.5
    # Trigger R-multiple = 1.0 (gain >= 10.0 pts -> price reaches 60.5)
    # Friction buffer = 1.0 pt -> stop ratchets to 50.5 + 1.0 = 51.5
    bars.loc[7, 'open'] = 50.0

    # At 09:23 (idx 8), price spikes up to 61.0 (> 60.5), triggering trailing stop
    # but low is 52.0 (does not hit the new 51.5 stop yet)
    bars.loc[8, 'open'] = 51.0
    bars.loc[8, 'high'] = 61.5
    bars.loc[8, 'low'] = 52.0
    bars.loc[8, 'close'] = 53.0

    # At 09:24 (idx 9), price drops back to low=50.0 (< 51.5 new stop, but > 40.5 old stop!)
    bars.loc[9, 'open'] = 53.0
    bars.loc[9, 'high'] = 53.5
    bars.loc[9, 'low'] = 50.0
    bars.loc[9, 'close'] = 50.5

    engine = ReversalReplayEngine()
    
    # 1. Without trailing stop: trade should stay alive at idx 9 and eventually exit on TIME
    res_no_trail = engine.replay_session(
        bars_df=bars,
        reference_level=48.0,
        date="2026-05-07",
        expiry="2026-05-07",
        strike=22500.0,
        option_type="CE",
        stop_points=10.0,
        target_points=20.0,
        max_hold_minutes=10,
    )
    assert res_no_trail.status == 'TRADE'
    assert res_no_trail.trade.exit_reason == 'TIME'

    # 2. With trailing stop enabled: trade must exit on SL at 09:24 (idx 9) at the ratcheted stop level 51.5!
    trailing_cfg = TrailingStopConfig(
        enabled=True,
        trigger_r_multiple=1.0,
        friction_buffer_points=1.0,
    )
    res_trail = engine.replay_session(
        bars_df=bars,
        reference_level=48.0,
        date="2026-05-07",
        expiry="2026-05-07",
        strike=22500.0,
        option_type="CE",
        stop_points=10.0,
        target_points=20.0,
        trailing_stop=trailing_cfg,
    )
    assert res_trail.status == 'TRADE'
    assert res_trail.trade.exit_reason == 'SL'
    # Exit fill should be stop_price - fees.slippage (51.5 - 0.5 = 51.0)
    assert res_trail.trade.exit_price == 51.0
    # Net gross pnl points: 51.0 - 50.5 = +0.5 points (protected profit!)
    assert res_trail.trade.gross_pnl_points == 0.5

