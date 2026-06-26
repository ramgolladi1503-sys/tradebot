import yfinance as yf
import pandas as pd
import numpy as np
from core.backtesting.wfa import WalkForwardAnalyzer
import argparse


def fetch_nifty_data(start_date="2010-01-01", end_date="2024-01-01"):
    print(f"Fetching NIFTY 50 data from Yahoo Finance ({start_date} to {end_date})...")
    ticker = yf.Ticker("^NSEI")
    df = ticker.history(start=start_date, end=end_date)

    # Clean and standardize columns
    df.columns = [col.lower() for col in df.columns]

    # Some older days might have missing data
    df = df.dropna(subset=["close"])

    # Ensure timezone naive for consistent processing
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)

    print(f"Fetched {len(df)} rows of real historical data.")
    return df


def run_wfa_on_real_data():
    df = fetch_nifty_data()

    if df.empty:
        print("Failed to fetch data.")
        return

    # We will run WFA with 3 years train, 1 year test, 0.2% slippage penalty
    wfa = WalkForwardAnalyzer(
        data=df, train_years=3, test_years=1, slippage_bps=20.0, spread_bps=0.0
    )

    # Grid search for strategy params
    param_grid = {
        "vol_target": [0.002, 0.005],
        "target_atr_mult": [1.0, 1.5, 2.0],
        "stop_atr_mult": [1.0, 1.5],
    }

    print("\nStarting Walk-Forward Analysis on REAL NIFTY DATA...")
    oos_trades = wfa.run(param_grid)

    if oos_trades.empty:
        print(
            "\nNo trades were generated in the Out-of-Sample periods. Strategy may not trigger on daily data."
        )
        return

    print("\n--- WFA OOS Performance Summary (Real Data) ---")
    total_oos_pnl = oos_trades["pl"].sum()
    win_rate = (oos_trades["pl"] > 0).mean() * 100
    total_trades = len(oos_trades)

    print(f"Total OOS PnL (after 20 bps slippage): {total_oos_pnl:.2f}")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {win_rate:.2f}%")

    if total_oos_pnl > 0:
        print(
            "\nCONCLUSION: SUCCESS! The strategy has a positive expectancy on real OOS data!"
        )
    else:
        print(
            "\nCONCLUSION: FAILURE. The strategy loses money on real OOS data. It was curve-fit to the dummy data."
        )


if __name__ == "__main__":
    run_wfa_on_real_data()
