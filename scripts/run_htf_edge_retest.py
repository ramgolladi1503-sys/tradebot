#!/usr/bin/env python3

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime, time
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.candidate_audits.htf_strategies import HTFStrategy
from core.candidate_audits.models import Candle, Signal, Rejection
from core.candidate_adapters.htf_adapter import build_htf_candidate_intents

DATA_DIR = REPO_ROOT / "data" / "backtest" / "one_minute"
STRATEGIES = [
    "OPENING_DRIVE_CONT",
    "15M_TREND_CONT",
    "15M_VWAP_PULLBACK",
    "FAILED_BREAKOUT_REVERSAL",
    "PDH_PDL_HOLD"
]

COST_PROFILES = {
    "zero_cost": 0.0,
    "cost_0_5": 0.5,
    "cost_0_8": 0.8,
    "cost_1_2": 1.2,
    "cost_1_5": 1.5,
    "cost_2_0": 2.0
}

def load_data():
    files = glob.glob(f"{DATA_DIR}/*.csv")
    dfs = []
    for f in sorted(files):
        df = pd.read_csv(f)
        dfs.append(df)
    
    if not dfs:
        return pd.DataFrame(), pd.DataFrame()
        
    df = pd.concat(dfs, ignore_index=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True).dt.tz_convert('Asia/Kolkata')
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    df['date'] = df['timestamp'].dt.date
    df['time'] = df['timestamp'].dt.time
    
    df['trend_15m'] = np.where(df['close'].ewm(span=15).mean().diff() > 0, 1, -1)
    df['trend_30m'] = np.where(df['close'].ewm(span=30).mean().diff() > 0, 1, -1)
    
    # create 15m df
    df_15m_list = []
    for d, group in df.groupby('date'):
        # group by 15min starting 09:15
        group = group.copy()
        group['15m_bin'] = group['timestamp'].dt.floor('15min') 
        # Actually NSE opens at 09:15, so 09:15 is already aligned to 15m boundaries.
        resampled = group.groupby('15m_bin').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).reset_index()
        resampled.rename(columns={'15m_bin': 'timestamp'}, inplace=True)
        resampled['date'] = d
        resampled['vwap'] = resampled['close'] # naive vwap
        df_15m_list.append(resampled)
        
    df_15m = pd.concat(df_15m_list, ignore_index=True)
    return df, df_15m

def main():
    print("Loading data...")
    df_1m, df_15m = load_data()
    
    if df_1m.empty:
        print("DATA_INSUFFICIENT")
        with open("docs/strategy_research/htf_final_classification.md", "w") as f:
            f.write("# HTF Final Classification\n\nDATA_INSUFFICIENT: No historical data found.")
        return

    print(f"Loaded {len(df_1m)} 1m bars and {len(df_15m)} 15m bars.")
    
    # Store trades per strategy
    all_trades = {s: [] for s in STRATEGIES}
    waterfall = {s: {"total_bars": 0, "candidate_emitted": 0, "safety_accepted": 0, "executable": 0} for s in STRATEGIES}
    
    df_1m['ts_str'] = df_1m['timestamp'].astype(str)
    
    # Pre-group df_1m by date for fast lookup
    df_1m_by_date = {d: group for d, group in df_1m.groupby('date')}
    
    print("Simulating strategies...")
    for s_name in STRATEGIES:
        strat = HTFStrategy(s_name)
        
        for i in range(len(df_15m)):
            if i < 1: continue
            
            c15 = df_15m.iloc[i]
            t = c15['timestamp']
            d = c15['date']
            
            t_close = t + pd.Timedelta(minutes=14)
            
            day_1m = df_1m_by_date.get(d)
            if day_1m is None or day_1m.empty: continue
            
            sub_1m = day_1m[day_1m['timestamp'] <= t_close]
            if sub_1m.empty: continue
            
            # c_15m and c_1m
            c_15m = Candle("NIFTY", c15['timestamp'], c15['open'], c15['high'], c15['low'], c15['close'], c15['volume'], c15['vwap'])
            c_1m_row = sub_1m.iloc[-1]
            c_1m = Candle("NIFTY", c_1m_row['timestamp'], c_1m_row['open'], c_1m_row['high'], c_1m_row['low'], c_1m_row['close'], c_1m_row['volume'], c_1m_row['close'])
            
            waterfall[s_name]["total_bars"] += 1
            
            # history slices (up to previous day or current day up to i)
            # Actually, the strategy evaluates using df_15m and df_1m.
            # Passing the full dataframe is bad practice for lookahead, but evaluate() usually only looks at iloc[-1] or iloc[-2]
            # We must pass the sliced dataframe.
            hist_15m = df_15m.iloc[:i+1]
            
            res = strat.evaluate(hist_15m, sub_1m, c_15m, c_1m, regime="VOL_EXPANSION")
            
            if isinstance(res, Signal):
                waterfall[s_name]["candidate_emitted"] += 1
                report = build_htf_candidate_intents(res)
                if report.eligible_intents:
                    waterfall[s_name]["safety_accepted"] += 1
                    waterfall[s_name]["executable"] += 1 # naive execution assumption
                    
                    # Track trade
                    all_trades[s_name].append({
                        "entry_time": t_close,
                        "entry_price": res.entry_price,
                        "target": res.target,
                        "stop_loss": res.stop_loss,
                        "direction": "CE" if res.target > res.entry_price else "PE",
                        "date": c15['date']
                    })
    
    print("Evaluating trades...")
    results = []
    
    for s_name in STRATEGIES:
        trades = all_trades[s_name]
        
        gross_pnl = []
        net_pnls = {k: [] for k in COST_PROFILES.keys()}
        
        for tr in trades:
            # Simulate exit
            entry_t = tr["entry_time"]
            entry_p = tr["entry_price"]
            tgt = tr["target"]
            sl = tr["stop_loss"]
            direction = tr["direction"]
            
            # get future 1m bars for the day
            day_1m = df_1m_by_date.get(tr["date"])
            future = day_1m[day_1m['timestamp'] > entry_t] if day_1m is not None else pd.DataFrame()
            
            month_key = entry_t.strftime("%Y-%m")
            
            exit_price = entry_p
            exit_reason = "EOD"
            for _, f_row in future.iterrows():
                high = f_row['high']
                low = f_row['low']
                t_val = f_row['time']
                
                # Check stops/targets
                if direction == "CE":
                    if low <= sl:
                        exit_price = sl
                        exit_reason = "STOP"
                        break
                    elif high >= tgt:
                        exit_price = tgt
                        exit_reason = "TARGET"
                        break
                else:
                    if high >= sl:
                        exit_price = sl
                        exit_reason = "STOP"
                        break
                    elif low <= tgt:
                        exit_price = tgt
                        exit_reason = "TARGET"
                        break
                
                if t_val >= time(15, 15):
                    exit_price = f_row['close']
                    exit_reason = "TIME_STOP"
                    break
            
            # EOD if not broken
            if exit_reason == "EOD" and not future.empty:
                exit_price = future.iloc[-1]['close']
                
            pts = (exit_price - entry_p) if direction == "CE" else (entry_p - exit_price)
            # scale by delta 0.5
            opts = pts * 0.5
            
            gross_pnl.append(opts)
            trades[trades.index(tr)]["opts"] = opts
            trades[trades.index(tr)]["exit_reason"] = exit_reason
            trades[trades.index(tr)]["month"] = month_key
            for k, cost in COST_PROFILES.items():
                net_pnls[k].append(opts - cost)
                
        # Stats
        if not gross_pnl:
            results.append({
                "Strategy": s_name,
                "Trades": 0,
                "Win_Rate": 0,
                "Gross_Exp": 0,
                "Realistic_Net_Exp": 0,
                "Status": "FEATURE_ONLY_NOT_EXECUTABLE"
            })
            continue
            
        wins = [p for p in gross_pnl if p > 0]
        losses = [p for p in gross_pnl if p <= 0]
        wr = len(wins) / len(gross_pnl)
        gx = np.mean(gross_pnl)
        rx = np.mean(net_pnls["cost_0_8"])
        
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        
        # Drawdown calculation
        cum_pnl = np.cumsum(net_pnls["cost_0_8"])
        peak = np.maximum.accumulate(cum_pnl)
        drawdown = peak - cum_pnl
        max_dd = np.max(drawdown) if len(drawdown) > 0 else 0
        
        status = "READY_FOR_PAPER_RETEST" if rx > 0 else "COST_KILLED_AFTER_CORRECT_IMPLEMENTATION"
        
        results.append({
            "Strategy": s_name,
            "Trades": len(gross_pnl),
            "Win_Rate": wr,
            "Gross_Exp": gx,
            "Realistic_Net_Exp": rx,
            "Avg_Win": avg_win,
            "Avg_Loss": avg_loss,
            "Max_DD": max_dd,
            "Status": status
        })
        
        # Monthly Stability
        monthly_data = {}
        for tr in trades:
            m = tr["month"]
            if m not in monthly_data:
                monthly_data[m] = []
            monthly_data[m].append(tr["opts"] - 0.8) # Net realistic
            
        # Exit Distribution
        exits = {"TARGET": 0, "STOP": 0, "TIME_STOP": 0, "EOD": 0}
        for tr in trades:
            exits[tr["exit_reason"]] += 1
            
        print(f"\n--- {s_name} ---")
        print(f"Trades: {len(gross_pnl)}")
        print(f"Exits: {exits}")
        print(f"Max DD (0.8pt cost): {max_dd:.2f}")
        for m in sorted(monthly_data.keys()):
            # only print summary of positive/negative months to keep output clean
            pass
        positive_months = sum(1 for m, vals in monthly_data.items() if np.sum(vals) > 0)
        total_months = len(monthly_data)
        print(f"Profitable Months: {positive_months} / {total_months}")
        
    res_df = pd.DataFrame(results)
    print(res_df)
    
    os.makedirs("docs/strategy_research", exist_ok=True)
    res_df.to_csv("docs/strategy_research/htf_cost_sensitivity.csv", index=False)
    
    wf_df = pd.DataFrame.from_dict(waterfall, orient='index').reset_index()
    wf_df.rename(columns={'index': 'Strategy'}, inplace=True)
    wf_df.to_csv("docs/strategy_research/htf_rejection_waterfall.csv", index=False)
    
    with open("docs/strategy_research/htf_final_classification.md", "w") as f:
        f.write("# HTF Final Classification\n\n")
        f.write("| Strategy | Trades | Win Rate | Gross Expectancy | Realistic Net | Status |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in results:
            f.write(f"| {r['Strategy']} | {r['Trades']} | {r['Win_Rate']:.2%} | {r['Gross_Exp']:.2f} | {r['Realistic_Net_Exp']:.2f} | {r['Status']} |\n")
            
    print("Done.")

if __name__ == "__main__":
    main()
