import os
import glob
import pandas as pd
from pathlib import Path
from core.backtesting.wfa import WalkForwardAnalyzer

def load_aeron7_nifty_f1():
    print("Finding all NIFTY_F1.txt files...")
    base_dir = Path("/Users/madhuram/tradebot/data/aeron7_data")
    files = list(base_dir.rglob("NIFTY_F1.txt"))
    
    # We may also have CSVs or others
    dfs = []
    print(f"Found {len(files)} files to process.")
    for f in files:
        try:
            df = pd.read_csv(f, names=['ticker', 'date', 'time', 'open', 'high', 'low', 'close', 'volume'])
            dfs.append(df)
        except Exception as e:
            print(f"Error reading {f}: {e}")
            
    if not dfs:
        print("No data found!")
        return pd.DataFrame()
        
    print("Concatenating files...")
    combined = pd.concat(dfs, ignore_index=True)
    
    print("Formatting datetime...")
    combined['date_str'] = combined['date'].astype(str)
    combined['time_str'] = combined['time'].astype(str)
    # Some dates might be like '20130301', some might be '01-03-2013' or '2013-03-01'
    # We will try to parse with a unified format or coerce
    combined['datetime'] = pd.to_datetime(combined['date_str'] + ' ' + combined['time_str'], errors='coerce')
    combined = combined.dropna(subset=['datetime'])
    combined.set_index('datetime', inplace=True)
    combined.sort_index(inplace=True)
    
    # Keep only OHLCV
    combined = combined[['open', 'high', 'low', 'close', 'volume']].astype(float)
    
    # Filter to 2017-2022 to keep it manageable and clean (5 years)
    combined = combined.loc['2017-01-01':'2022-12-31']
    
    # Resample to 5-minute to speed up analysis if 1-min is too noisy/slow, or just keep 1-min. Let's keep 5-min for realistic slippage.
    # Actually let's use 5-minute data to remove micro-noise.
    print("Resampling to 5-minute bars...")
    ohlc_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    combined = combined.resample('5min').agg(ohlc_dict).dropna()
    
    print(f"Loaded {len(combined)} 5-minute bars from 2017 to 2022.")
    return combined

def run_intraday_wfa():
    df = load_aeron7_nifty_f1()
    if df.empty:
        return
        
    wfa = WalkForwardAnalyzer(
        data=df,
        train_years=2,
        test_years=1,
        slippage_bps=5.0, # Realistic NIFTY Futures slippage
        spread_bps=0.0
    )
    
    param_grid = {
        "vol_target": [0.002, 0.005],
        "target_atr_mult": [1.5, 2.0, 3.0],
        "stop_atr_mult": [1.0, 1.5]
    }
    
    print("\nStarting Intraday Walk-Forward Analysis (5-min timeframe)...")
    oos_trades = wfa.run(param_grid)
    
    if oos_trades.empty:
        print("\nNo OOS trades generated.")
        return
        
    print("\n--- WFA OOS Performance Summary (Intraday Real Data) ---")
    total_oos_pnl = oos_trades['pl'].sum()
    win_rate = (oos_trades['pl'] > 0).mean() * 100
    total_trades = len(oos_trades)
    
    print(f"Total OOS PnL (after 5 bps slippage): {total_oos_pnl:.2f}")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {win_rate:.2f}%")
    
if __name__ == "__main__":
    run_intraday_wfa()
