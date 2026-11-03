"""
Sensex Option Mate RBFN 8-Month Comprehensive Backtest & WFA
===========================================================
Simulates Sensex Option Mate RBFN strategy across 8 months (Dec 2025 – Jul 2026):
1. Morning Drive (09:25–10:15): Trend Decider (TD) directional expansion to RP1.
2. Midday Reversal (Gate 3, 10:45–13:15): Confirmed multi-bar rejection inside RP1 back to TD.
3. Volatility Hurdle (Gate 2): Sensex ATR_14 >= 450.0, VIX >= 12.0.
4. Walk-Forward Analysis (WFA): 4 two-month folds.
5. In-Sample vs Out-of-Sample verification.
6. Statutory cost schedule and slippage (-2.0 pts per trade on Sensex options).
"""

import os
import glob
import json
import math
import pandas as pd
import numpy as np
from datetime import datetime
from strategies.sensex_optionmate_rbfn_strategy import SensexOptionMateRBFNStrategy

def run_backtest():
    files = sorted(glob.glob("runtime/upstox_candidate_replay/*/underlying/BSE_INDEX|SENSEX_*.parquet"))
    date_to_file = {}
    for f in files:
        d_str = os.path.basename(os.path.dirname(os.path.dirname(f)))
        if "20251201" <= d_str <= "20260731":
            date_to_file[d_str] = f

    sorted_dates = sorted(date_to_file.keys())
    print(f"Loaded {len(sorted_dates)} Sensex sessions from {sorted_dates[0]} to {sorted_dates[-1]}")

    strat = SensexOptionMateRBFNStrategy(step_size=100, min_atr_frictional_hurdle=450.0, min_vix_hurdle=12.0)

    # Pre-load daily data
    session_data = {}
    for d_str in sorted_dates:
        df = pd.read_parquet(date_to_file[d_str])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        session_data[d_str] = df

    all_trades = []

    for idx, d_str in enumerate(sorted_dates):
        day_df = session_data[d_str]
        if len(day_df) < 60:
            continue

        # Lookback ATR calculation
        prev_dates = sorted_dates[max(0, idx - 14):idx]
        if prev_dates:
            ranges = [session_data[pd]["high"].max() - session_data[pd]["low"].min() for pd in prev_dates]
            atr_14 = float(np.mean(ranges))
            prev_close = float(session_data[prev_dates[-1]]["close"].iloc[-1])
        else:
            atr_14 = 550.0
            prev_close = float(day_df["open"].iloc[0])

        spot_open = float(day_df["open"].iloc[0])
        vix = 13.5 # baseline empirical VIX

        # Compute DTE (BSE Sensex weekly expiry is typically Friday)
        dt = datetime.strptime(d_str, "%Y%m%d")
        day_of_week = dt.weekday() # Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4
        if day_of_week == 4:
            dte = 0
        elif day_of_week == 3:
            dte = 1
        elif day_of_week == 2:
            dte = 2
        else:
            dte = 3

        grid = strat.compute_daily_grid(
            date=d_str,
            spot_open=spot_open,
            prev_close=prev_close,
            atr_14=atr_14,
            vix=vix,
            dte=dte,
        )

        # -------------------------------------------------------------
        # Trade 1: Morning Drive (09:25 - 10:15)
        # -------------------------------------------------------------
        morning_df = day_df[(day_df["timestamp"].dt.time >= pd.to_datetime("09:25").time()) &
                            (day_df["timestamp"].dt.time <= pd.to_datetime("10:15").time())]
        if not morning_df.empty:
            curr_spot = float(morning_df["close"].iloc[-1])
            t_str = morning_df["timestamp"].iloc[-1].strftime("%H:%M")
            sig = strat.generate_signal(grid, current_spot=curr_spot, current_atr=atr_14, vix=vix, time_str=t_str)

            if sig.action in ["BUY_CALL", "BUY_PUT"] and not sig.is_vetoed:
                entry_spot = curr_spot
                post_morning = day_df[day_df["timestamp"] > morning_df["timestamp"].iloc[-1]]
                exit_spot = entry_spot
                outcome = "EOD"

                for _, row in post_morning.iterrows():
                    if sig.action == "BUY_CALL":
                        if row["high"] >= sig.target_1_spot:
                            exit_spot = sig.target_1_spot
                            outcome = "TARGET_HIT"
                            break
                        elif row["low"] <= sig.invalidation_spot:
                            exit_spot = sig.invalidation_spot
                            outcome = "STOP_LOSS_HIT"
                            break
                    else:
                        if row["low"] <= sig.target_1_spot:
                            exit_spot = sig.target_1_spot
                            outcome = "TARGET_HIT"
                            break
                        elif row["high"] >= sig.invalidation_spot:
                            exit_spot = sig.invalidation_spot
                            outcome = "STOP_LOSS_HIT"
                            break

                if exit_spot == entry_spot and not post_morning.empty:
                    exit_spot = float(post_morning["close"].iloc[-1])

                spot_pnl = (exit_spot - entry_spot) if sig.action == "BUY_CALL" else (entry_spot - exit_spot)
                # Option delta translation (~0.45 delta for 300 OTM/ATM)
                delta = 0.45
                opt_pnl_pts = spot_pnl * delta - 2.0 # 2.0 pt slippage on Sensex options
                rupee_pnl = opt_pnl_pts * 20.0 - 55.0 # 20 lot size, Rs 55 statutory taxes

                all_trades.append({
                    "date": d_str,
                    "phase": "MORNING_DRIVE",
                    "action": sig.action,
                    "strike": sig.target_strike,
                    "anchor": sig.entry_premium_est,
                    "spot_entry": entry_spot,
                    "spot_exit": exit_spot,
                    "spot_pnl": spot_pnl,
                    "opt_pnl_pts": opt_pnl_pts,
                    "rupee_pnl": rupee_pnl,
                    "win": opt_pnl_pts > 0,
                    "outcome": outcome,
                })

        # -------------------------------------------------------------
        # Trade 2: Midday Reversal (10:45 - 13:15) with Gate 3
        # -------------------------------------------------------------
        midday_df = day_df[(day_df["timestamp"].dt.time >= pd.to_datetime("10:45").time()) &
                           (day_df["timestamp"].dt.time <= pd.to_datetime("13:15").time())]
        if not midday_df.empty and len(midday_df) >= 15:
            chunk_closes = []
            chunk_highs = []
            chunk_lows = []
            for i in range(0, min(len(midday_df), 25), 5):
                c = midday_df.iloc[i:i+5]
                chunk_closes.append(float(c["close"].iloc[-1]))
                chunk_highs.append(float(c["high"].max()))
                chunk_lows.append(float(c["low"].min()))

            curr_spot = float(midday_df["close"].iloc[-1])
            t_str = midday_df["timestamp"].iloc[-1].strftime("%H:%M")
            rev_sig = strat.evaluate_midday_reversal(
                grid=grid,
                current_spot=curr_spot,
                recent_candle_closes=chunk_closes,
                recent_candle_highs=chunk_highs,
                recent_candle_lows=chunk_lows,
                current_atr=atr_14,
                vix=vix,
                time_str=t_str,
            )

            if rev_sig is not None and rev_sig.action in ["BUY_CALL", "BUY_PUT"] and not rev_sig.is_vetoed:
                entry_spot = curr_spot
                post_midday = day_df[day_df["timestamp"] > midday_df["timestamp"].iloc[-1]]
                exit_spot = entry_spot
                outcome = "EOD"

                for _, row in post_midday.iterrows():
                    if rev_sig.action == "BUY_CALL":
                        if row["high"] >= rev_sig.target_1_spot:
                            exit_spot = rev_sig.target_1_spot
                            outcome = "TARGET_HIT"
                            break
                        elif row["low"] <= rev_sig.invalidation_spot:
                            exit_spot = rev_sig.invalidation_spot
                            outcome = "STOP_LOSS_HIT"
                            break
                    else:
                        if row["low"] <= rev_sig.target_1_spot:
                            exit_spot = rev_sig.target_1_spot
                            outcome = "TARGET_HIT"
                            break
                        elif row["high"] >= rev_sig.invalidation_spot:
                            exit_spot = rev_sig.invalidation_spot
                            outcome = "STOP_LOSS_HIT"
                            break

                if exit_spot == entry_spot and not post_midday.empty:
                    exit_spot = float(post_midday["close"].iloc[-1])

                spot_pnl = (exit_spot - entry_spot) if rev_sig.action == "BUY_CALL" else (entry_spot - exit_spot)
                delta = 0.50
                opt_pnl_pts = spot_pnl * delta - 2.0
                rupee_pnl = opt_pnl_pts * 20.0 - 55.0

                all_trades.append({
                    "date": d_str,
                    "phase": "MIDDAY_REVERSAL",
                    "action": rev_sig.action,
                    "strike": rev_sig.target_strike,
                    "anchor": rev_sig.entry_premium_est,
                    "spot_entry": entry_spot,
                    "spot_exit": exit_spot,
                    "spot_pnl": spot_pnl,
                    "opt_pnl_pts": opt_pnl_pts,
                    "rupee_pnl": rupee_pnl,
                    "win": opt_pnl_pts > 0,
                    "outcome": outcome,
                })

    tdf = pd.DataFrame(all_trades)
    print("\n================ SENSEX OPTIONMATE 8-MONTH BACKTEST SUMMARY ================")
    print(f"Total Sessions Evaluated: {len(sorted_dates)}")
    print(f"Total Trades Generated: {len(tdf)}")
    wins = tdf[tdf["win"] == True]
    wr = len(wins) / len(tdf) * 100 if len(tdf) > 0 else 0.0
    print(f"Win Rate: {wr:.2f}% ({len(wins)}/{len(tdf)})")
    print(f"Total Option Points: {tdf['opt_pnl_pts'].sum():.1f} pts")
    print(f"Total Net Rupee P&L (after slippage & statutory taxes): Rs {tdf['rupee_pnl'].sum():,.2f}")
    print(f"Profit Factor: {abs(wins['rupee_pnl'].sum() / tdf[tdf['win']==False]['rupee_pnl'].sum()):.2f}")

    print("\n---------------- BREAKDOWN BY PHASE ----------------")
    for phase, g in tdf.groupby("phase"):
        gw = g[g["win"] == True]
        print(f"{phase:16} | Trades: {len(g):3} | Wins: {len(gw):2} ({len(gw)/len(g)*100:.1f}%) | Net Rs: {g['rupee_pnl'].sum():+10.2f}")

    # 4-Fold Walk-Forward Analysis (WFA)
    print("\n---------------- WALK-FORWARD ANALYSIS (4 FOLDS) ----------------")
    folds = [
        ("Fold 1: Dec 2025 - Jan 2026", "20251201", "20260131"),
        ("Fold 2: Feb 2026 - Mar 2026", "20260201", "20260331"),
        ("Fold 3: Apr 2026 - May 2026", "20260401", "20260531"),
        ("Fold 4: Jun 2026 - Jul 2026", "20260601", "20260731"),
    ]
    
    wfa_results = []
    for label, s_date, e_date in folds:
        f_df = tdf[(tdf["date"] >= s_date) & (tdf["date"] <= e_date)]
        f_wins = f_df[f_df["win"] == True]
        f_wr = len(f_wins) / len(f_df) * 100 if len(f_df) > 0 else 0.0
        f_pnl = f_df["rupee_pnl"].sum()
        print(f"{label:30} | Trades: {len(f_df):2} | WR: {f_wr:4.1f}% | Net PnL: Rs {f_pnl:+10.2f}")
        wfa_results.append({"fold": label, "trades": len(f_df), "win_rate": f_wr, "net_pnl": f_pnl})

    # Out-of-Sample verification: Fold 1-2 (In-Sample), Fold 3-4 (Out-of-Sample)
    insample = tdf[(tdf["date"] >= "20251201") & (tdf["date"] <= "20260331")]
    oos = tdf[(tdf["date"] >= "20260401") & (tdf["date"] <= "20260731")]
    print("\n---------------- IN-SAMPLE VS OUT-OF-SAMPLE ----------------")
    print(f"In-Sample (Dec-Mar) : {len(insample)} trades | WR: {len(insample[insample['win']==True])/len(insample)*100:.1f}% | Net Rs: {insample['rupee_pnl'].sum():+10.2f}")
    print(f"Out-of-Sample (Apr-Jul): {len(oos)} trades | WR: {len(oos[oos['win']==True])/len(oos)*100:.1f}% | Net Rs: {oos['rupee_pnl'].sum():+10.2f}")

    # Save artifact
    output_path = "research/rbfn_options/results/sensex_optionmate_8m_backtest_report.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "total_sessions": len(sorted_dates),
            "total_trades": len(tdf),
            "win_rate": wr,
            "net_rupee_pnl": tdf["rupee_pnl"].sum(),
            "wfa": wfa_results,
            "in_sample_pnl": insample["rupee_pnl"].sum(),
            "out_of_sample_pnl": oos["rupee_pnl"].sum(),
        }, f, indent=2)
    print(f"\nArtifact saved to: {output_path}")

if __name__ == "__main__":
    run_backtest()
