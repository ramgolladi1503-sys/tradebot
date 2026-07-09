#!/usr/bin/env python3
import os
import json
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

def process_tick_file(tick_file_path):
    """Read a tick parquet file and resample all symbols to 1-minute OHLC."""
    print(f"Loading tick file: {tick_file_path}")
    df_ticks = pd.read_parquet(tick_file_path)
    
    if df_ticks['ts'].max() > 1e11: # likely ms
        df_ticks['timestamp'] = pd.to_datetime(df_ticks['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
    else:
        df_ticks['timestamp'] = pd.to_datetime(df_ticks['ts'], unit='s', utc=True).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
        
    df_ticks = df_ticks.set_index('timestamp')
    df_ticks = df_ticks.sort_index()
    
    # Resample all symbols at once
    ohlc_dict = {}
    symbols = df_ticks['symbol'].unique()
    for sym in symbols:
        df_sym = df_ticks[df_ticks['symbol'] == sym]
        ohlc = df_sym['ltp'].resample('1min').ohlc()
        ohlc = ohlc.dropna().reset_index()
        ohlc['symbol'] = sym
        ohlc_dict[sym] = ohlc
        
    return ohlc_dict

def determine_daily_regime(df):
    """Analyze the full day OHLC to determine the overall market regime."""
    if len(df) < 10:
        return "Insufficient Data", "Not enough bars."
        
    day_open = df.iloc[0]['open']
    day_close = df.iloc[-1]['close']
    day_high = df['high'].max()
    day_low = df['low'].min()
    
    net_move = abs(day_close - day_open)
    total_range = day_high - day_low
    
    if total_range == 0:
        return "Flat", "Zero range."
        
    df_copy = df.copy()
    df_copy['5m_change'] = df_copy['close'].diff(5).abs()
    path_length = df_copy['5m_change'].sum()
    
    efficiency = net_move / total_range if total_range > 0 else 0
    
    if efficiency > 0.6:
        direction = "UpTrend" if day_close > day_open else "DownTrend"
        return f"Directional {direction}", f"High efficiency ({efficiency:.2f}). Market trended powerfully with minimal overlap."
    elif total_range < (day_open * 0.01): # 1% for options might still be tight
        return "Low Volatility Chop", f"Tight range ({total_range:.2f} pts). Price constricted."
    else:
        return "Wide Range Mean Reverting", f"Low efficiency ({efficiency:.2f}) but wide range. Heavy two-way swings."

def oracle_optimal_swings(df, threshold_pct=0.5):
    """Finds the 'Gold Standard' structural swings in hindsight. For options, use a slightly wider threshold."""
    if len(df) < 10:
        return []
        
    trades = []
    mode = 0 
    extreme_price = df.iloc[0]['close']
    extreme_idx = 0
    swings = []
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if mode == 0:
            if price > extreme_price * (1 + threshold_pct/100):
                mode = 1
                extreme_price = price
                extreme_idx = i
            elif price < extreme_price * (1 - threshold_pct/100):
                mode = -1
                extreme_price = price
                extreme_idx = i
        elif mode == 1:
            if price > extreme_price:
                extreme_price = price
                extreme_idx = i
            elif price < extreme_price * (1 - threshold_pct/100):
                swings.append((extreme_idx, extreme_price, "PEAK"))
                mode = -1
                extreme_price = price
                extreme_idx = i
        elif mode == -1:
            if price < extreme_price:
                extreme_price = price
                extreme_idx = i
            elif price > extreme_price * (1 + threshold_pct/100):
                swings.append((extreme_idx, extreme_price, "TROUGH"))
                mode = 1
                extreme_price = price
                extreme_idx = i
                
    swings.append((extreme_idx, extreme_price, "PEAK" if mode == 1 else "TROUGH"))
    
    position = 0
    entry_price = 0.0
    
    for idx, price, s_type in swings:
        row = df.iloc[idx]
        if s_type == "TROUGH":
            if position == -1:
                pnl = entry_price - price
                reasoning = f"Oracle Exit: Major structural support formed. Extracting max downside value."
                trades.append({"time": str(row['timestamp']), "type": "EXIT", "price": round(price, 2), "pnl": round(pnl, 2), "strategy": "OracleSwing", "reasoning": reasoning})
                position = 0
            reasoning = f"Oracle Entry: Absolute local trough identified. High probability structural bounce."
            trades.append({"time": str(row['timestamp']), "type": "BUY", "price": round(price, 2), "strategy": "OracleSwing", "reasoning": reasoning})
            position = 1
            entry_price = price
        elif s_type == "PEAK":
            if position == 1:
                pnl = price - entry_price
                reasoning = f"Oracle Exit: Major structural resistance formed. Extracting max upside value."
                trades.append({"time": str(row['timestamp']), "type": "EXIT", "price": round(price, 2), "pnl": round(pnl, 2), "strategy": "OracleSwing", "reasoning": reasoning})
                position = 0
            reasoning = f"Oracle Entry: Absolute local peak identified. High probability structural rejection."
            trades.append({"time": str(row['timestamp']), "type": "SELL", "price": round(price, 2), "strategy": "OracleSwing", "reasoning": reasoning})
            position = -1
            entry_price = price
            
    if position != 0:
        last_row = df.iloc[-1]
        pnl = (last_row['close'] - entry_price) if position == 1 else (entry_price - last_row['close'])
        trades.append({"time": str(last_row['timestamp']), "type": "EXIT", "price": round(last_row['close'], 2), "pnl": round(pnl, 2), "strategy": "OracleSwing", "reasoning": "Oracle EOD Force Exit."})

    return trades

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y%m%d"), help="Date in YYYYMMDD")
    parser.add_argument("--tick-file", type=str, default="", help="Path to raw ticks parquet file to evaluate")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing output")
    args = parser.parse_args()
    
    print(f"Generating Advanced Oracle Evaluator Report for: {args.date}")
    
    if not args.tick_file or not Path(args.tick_file).exists():
        print(f"Error: Tick file {args.tick_file} not found.")
        return

    ohlc_dict = process_tick_file(args.tick_file)
    
    report_data = []
    
    for sym, df in ohlc_dict.items():
        if df.empty or len(df) < 30: # Skip very illiquid options
            continue
            
        is_option = " CE " in sym or " PE " in sym
        if not is_option:
            continue
            
        regime_name, regime_reason = determine_daily_regime(df)
        
        # Options are more volatile, so we use a higher threshold to avoid noise
        oracle_trades = oracle_optimal_swings(df, threshold_pct=5.0) 
        
        if not oracle_trades:
            continue
            
        total_pnl = sum(t.get('pnl', 0) for t in oracle_trades if t['type'] == 'EXIT')
        
        report_data.append({
            "Symbol": sym,
            "DayRegime": regime_name,
            "RegimeReasoning": regime_reason,
            "OracleMaxTheoreticalPNL": round(total_pnl, 2),
            "TradeCount": len(oracle_trades) // 2,
            "OracleTrades": oracle_trades
        })
        
    # Sort by Max PNL descending
    report_data = sorted(report_data, key=lambda x: x['OracleMaxTheoreticalPNL'], reverse=True)
    
    report = {
        "date": args.date,
        "evaluation_timestamp": datetime.now().isoformat(),
        "concept": "Oracle Gold Standard Evaluator - Finds optimal structural swings retrospectively to benchmark live bots against.",
        "source_file": args.tick_file,
        "results": report_data[:50] # Top 50 options to keep JSON manageable
    }
    
    if args.dry_run:
        print("Dry run complete. Found {} profitable options.".format(len(report_data)))
    else:
        out_path = Path(f"reports/oracle_options_predictions_report_{args.date}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Oracle Report written to {out_path}")

if __name__ == "__main__":
    main()
