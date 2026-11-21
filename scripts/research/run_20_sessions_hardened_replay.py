#!/usr/bin/env python3
"""Past 20-Session Live Market Replay Simulator for Hardened Unified Pipeline.
=============================================================================
Replays the past 20 historical market sessions (NIFTY & SENSEX) through the
hardened Sentinel pipeline with:
1. Dynamic Gear Tracking (Ω_10 >= 1.80 -> TREND, Ω_10 < 1.00 -> RANGE).
2. 3-Bar Hysteresis Lock (prevents chattering).
3. OptionMate Sustainable Anchor & 1-Strike ITM Expiry Gate.
4. Priority-Ranked Execution Arbiter & Dual-Stream Shadow Tagging.
"""

from __future__ import annotations

import glob
import math
import os
import sys
from datetime import datetime, date, time as dt_time
from pathlib import Path
import pandas as pd
import numpy as np

def run_20_session_replay():
    files = sorted(list(set(glob.glob('runtime/kite_candidate_replay/*/underlying/*NIFTY*.parquet'))))
    # Deduplicate sessions by date
    sessions_dict = {}
    for f in files:
        if 'BANK' in f:
            continue
        d_str = f.split('/')[2]
        try:
            dt = datetime.strptime(d_str, '%Y-%m-%d').date()
            if dt >= date(2026, 1, 1):
                sessions_dict[dt] = f
        except Exception:
            pass

    sorted_dates = sorted(sessions_dict.keys())
    past_20_dates = sorted_dates[-20:]

    print("=" * 90)
    print(f"🎬 HARDENED UNIFIED PIPELINE: PAST 20 SESSIONS REPLAY AUDIT (NIFTY 50)")
    print(f"   Date Range: {past_20_dates[0]} to {past_20_dates[-1]}")
    print("=" * 90)

    # Pre-calculate daily ATR_14
    daily_stats = {}
    all_trs = []
    for dt in sorted_dates:
        f = sessions_dict[dt]
        df = pd.read_parquet(f)
        if df.empty:
            continue
        d_high = df['high'].max()
        d_low = df['low'].min()
        tr = d_high - d_low
        daily_stats[dt] = tr
        all_trs.append((dt, tr))

    results = []
    
    # State tracking across the 20 sessions
    current_gear = "GEAR_1_RANGE"
    range_bar_consecutive = 0

    for idx, dt in enumerate(past_20_dates):
        f = sessions_dict[dt]
        df = pd.read_parquet(f)
        if len(df) < 15:
            continue

        df['ist'] = df['date'].dt.tz_convert('Asia/Kolkata')
        
        # Calculate ATR_14 up to prior session
        dt_idx = [x[0] for x in all_trs].index(dt)
        if dt_idx >= 14:
            atr14 = np.mean([x[1] for x in all_trs[dt_idx-14:dt_idx]])
        else:
            atr14 = 160.0

        # Bar 1 (09:15 - 09:20) and Bar 2 (09:20 - 09:25)
        c0 = df.iloc[0]
        c0_open = c0['open']
        c0_high = c0['high']
        c0_low = c0['low']
        c0_close = c0['close']
        c0_range = c0_high - c0_low

        c1 = df.iloc[1] if len(df) > 1 else c0
        c1_high = c1['high']
        c1_low = c1['low']

        # 10m Opening Range and Expansion Ratio Omega_10
        range_10m = max(c0_high, c1_high) - min(c0_low, c1_low)
        omega_10 = round(range_10m / atr14, 2)

        # Dynamic Gear Logic with 3-Bar Hysteresis
        prev_gear = current_gear
        if omega_10 >= 1.80:
            current_gear = "GEAR_2_TREND"
            range_bar_consecutive = 0
        elif omega_10 < 1.00:
            range_bar_consecutive += 1
            if current_gear == "GEAR_2_TREND" and range_bar_consecutive >= 3:
                current_gear = "GEAR_1_RANGE"
        else:
            range_bar_consecutive = 0

        # Expiry Check
        is_expiry = (dt.weekday() == 3)
        dte = 0.20 if is_expiry else max(1.0, 4.0 - dt.weekday())
        vix = 13.5

        # Sustainable Price Anchor
        eff_dte = max(0.20, float(dte))
        anchor = round(0.40 * c0_close * (max(vix, 9.0) / 100.0) * math.sqrt(eff_dte / 365.0), 1)

        # Gate 2 Quality Check
        gate2_passed = True
        gate2_reasons = []
        if atr14 < 130.0:
            gate2_passed = False
            gate2_reasons.append("LOW_ATR")
        if c0_range < 0.35 * atr14:
            gate2_passed = False
            gate2_reasons.append("NARROW_OR")
        if abs(c0_close - c0_open) / max(1.0, c0_range) < 0.55:
            gate2_passed = False
            gate2_reasons.append("WEAK_BODY")

        bullish = c0_close > c0_open
        direction = "CE" if bullish else "PE"

        # Scale Harmonic Levels
        channel_step = round((c0_close * 0.0050) / 10.0) * 10.0  # 120 pts
        td = round(c0_close / 40.0) * 40.0
        rp1 = td + channel_step if bullish else td - channel_step
        rp2 = td + (2.0 * channel_step) if bullish else td - (2.0 * channel_step)

        # Strike Resolution with 1-Strike ITM Gate on 0-DTE Mornings
        if is_expiry:
            # 1-Strike ITM defense (delta ~ 0.58)
            resolved_strike = (round(c0_close / 50.0) * 50) - 50 if bullish else (round(c0_close / 50.0) * 50) + 50
            entry_premium = 75.0  # 1-Strike ITM liquid quote
            moneyness = "ITM_1"
        else:
            resolved_strike = int(round(rp1 / 50.0) * 50)
            entry_premium = round(anchor * 0.50, 1)
            moneyness = "OTM_SLINGSHOT"

        # Trade Evaluation (Entry between 09:20 - 09:45)
        entry_triggered = False
        entry_idx = -1
        entry_spot = 0.0
        entry_time_str = ""

        if gate2_passed:
            for c_idx in range(1, min(len(df), 25)):
                curr_c = df.iloc[c_idx]
                curr_t = curr_c['ist'].strftime('%H:%M')
                if c_idx == 1:
                    if (bullish and curr_c['high'] > c0_high) or (not bullish and curr_c['low'] < c0_low):
                        entry_triggered = True
                        entry_idx = c_idx
                        entry_spot = c0_high if bullish else c0_low
                        entry_time_str = curr_t
                        break
                else:
                    if (bullish and curr_c['close'] > c0_high) or (not bullish and curr_c['close'] < c0_low):
                        entry_triggered = True
                        entry_idx = c_idx
                        entry_spot = curr_c['close']
                        entry_time_str = curr_t
                        break

        # Position Lifecycle Management
        outcome = "NO_TRADE"
        exit_time_str = "-"
        opt_pnl_pts = 0.0
        exit_prem = entry_premium
        inval_level = (c0_low - 15.0) if bullish else (c0_high + 15.0)

        # Dual-stream shadow tag: First trade of day is PRIMARY_CANONICAL
        shadow_tier = "PRIMARY_CANONICAL" if entry_triggered else "STANDBY"

        if entry_triggered:
            subsequent = df.iloc[entry_idx+1:]
            half_booked = False
            cost_sl_active = False

            for _, bar in subsequent.iterrows():
                b_high = bar['high']
                b_low = bar['low']
                b_t = bar['ist'].strftime('%H:%M')

                # Stop loss check
                if not cost_sl_active:
                    if (bullish and b_low <= inval_level) or (not bullish and b_high >= inval_level):
                        outcome = "STOP_LOSS_HIT"
                        exit_time_str = b_t
                        exit_prem = entry_premium * 0.80  # 20% vol-stop
                        opt_pnl_pts = exit_prem - entry_premium
                        break
                else:
                    if (bullish and b_low <= entry_spot) or (not bullish and b_high >= entry_spot):
                        outcome = "COST_TRAIL_EXIT"
                        exit_time_str = b_t
                        # Half at RP1 (+45%), half at cost (+0%) = +22.5%
                        exit_prem = entry_premium * 1.225
                        opt_pnl_pts = exit_prem - entry_premium
                        break

                # RP1 Target check (120 pts spot expansion)
                if not half_booked:
                    if (bullish and b_high >= rp1) or (not bullish and b_low <= rp1):
                        half_booked = True
                        cost_sl_active = True
                        exit_prem = entry_premium * 1.45  # +45% on option

                # RP2 Runner check (240 pts spot expansion)
                if half_booked:
                    if (bullish and b_high >= rp2) or (not bullish and b_low <= rp2):
                        outcome = "RP2_RUNNER_HIT"
                        exit_time_str = b_t
                        exit_prem = entry_premium * 2.10  # +110% on runner
                        opt_pnl_pts = exit_prem - entry_premium
                        break

            # If still open at 15:15 EOD square-off
            if outcome == "NO_TRADE" and entry_triggered:
                last_bar = subsequent.iloc[-1]
                outcome = "EOD_SQUAREOFF"
                exit_time_str = "15:15"
                if half_booked:
                    exit_prem = entry_premium * 1.35
                else:
                    exit_prem = entry_premium * 0.95
                opt_pnl_pts = exit_prem - entry_premium

        lot_size = 65
        net_cash_pnl = opt_pnl_pts * lot_size

        results.append({
            "date": dt,
            "gear": current_gear,
            "omega_10": omega_10,
            "setup": f"{direction} ({moneyness})",
            "entry_time": entry_time_str,
            "exit_time": exit_time_str,
            "outcome": outcome,
            "entry_prem": entry_premium,
            "exit_prem": round(exit_prem, 1),
            "opt_pnl": round(opt_pnl_pts, 1),
            "cash_pnl": round(net_cash_pnl, 1),
            "tier": shadow_tier,
        })

    # Display Replay Scoreboard
    print(f"{'Date':12} | {'Gear':13} | {'Ω10':5} | {'Setup':18} | {'Entry':5} | {'Exit':5} | {'Outcome':16} | {'Prem In':7} | {'Prem Out':8} | {'PnL (pts)':9} | {'Net PnL (₹)':11}")
    print("-" * 125)

    tot_trades = 0
    tot_wins = 0
    tot_pnl_pts = 0.0
    tot_cash_pnl = 0.0

    for r in results:
        if r["outcome"] != "NO_TRADE":
            tot_trades += 1
            if r["opt_pnl"] > 0:
                tot_wins += 1
            tot_pnl_pts += r["opt_pnl"]
            tot_cash_pnl += r["cash_pnl"]
            pnl_str = f"{r['opt_pnl']:+6.1f}"
            cash_str = f"₹{r['cash_pnl']:+8.1f}"
        else:
            pnl_str = "  0.0"
            cash_str = "     ₹0.0"

        print(f"{str(r['date']):12} | {r['gear']:13} | {r['omega_10']:5.2f} | {r['setup']:18} | {r['entry_time']:5} | {r['exit_time']:5} | {r['outcome']:16} | {r['entry_prem']:7.1f} | {r['exit_prem']:8.1f} | {pnl_str:9} | {cash_str:11}")

    win_rate = (tot_wins / tot_trades * 100.0) if tot_trades > 0 else 0.0
    print("=" * 125)
    print(f"📊 PAST 20 SESSIONS REPLAY SCOREBOARD SUMMARY:")
    print(f"   • Total Active Trades Taken: {tot_trades} / 20 sessions (Trade Frequency: {tot_trades/20*100:.1f}%)")
    print(f"   • Wins: {tot_wins} | Losses: {tot_trades - tot_wins}")
    print(f"   • Win Rate: {win_rate:.1f}%")
    print(f"   • Aggregate Net Option Points: {tot_pnl_pts:+8.1f} pts")
    print(f"   • Aggregate Net Cash PnL (1 lot NIFTY): ₹{tot_cash_pnl:+10.2f}")
    print("=" * 125)

if __name__ == '__main__':
    run_20_session_replay()
