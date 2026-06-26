#!/usr/bin/env python3
import os
import sys
import argparse
import pandas as pd
import numpy as np

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.backtesting.wfa import WalkForwardAnalyzer


def generate_dummy_data(years=5):
    """Generates 5 years of daily dummy OHLCV data for testing."""
    np.random.seed(42)
    dates = pd.date_range(start="2019-01-01", periods=252 * years, freq="B")

    # Random walk
    returns = np.random.normal(0.0005, 0.01, size=len(dates))
    closes = 10000 * np.exp(np.cumsum(returns))

    highs = closes * (1 + np.abs(np.random.normal(0, 0.005, size=len(dates))))
    lows = closes * (1 - np.abs(np.random.normal(0, 0.005, size=len(dates))))
    opens = closes * (1 + np.random.normal(0, 0.002, size=len(dates)))
    volumes = np.random.randint(100000, 1000000, size=len(dates))

    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )

    return df


def main():
    parser = argparse.ArgumentParser(description="Run Walk-Forward Analysis")
    parser.add_argument(
        "--data", type=str, help="Path to CSV containing historical data"
    )
    parser.add_argument(
        "--slippage-bps", type=float, default=20.0, help="Slippage in bps (20.0 = 0.2%)"
    )
    args = parser.parse_args()

    print(f"--- Starting Walk-Forward Analysis ---")
    print(f"Strict Slippage: {args.slippage_bps} bps per fill")

    if args.data and os.path.exists(args.data):
        print(f"Loading data from {args.data}...")
        df = pd.read_csv(args.data, parse_dates=True, index_col=0)
    else:
        print(
            "No valid data path provided. Generating 5 years of synthetic OHLCV data..."
        )
        df = generate_dummy_data(years=5)

    print(
        f"Data shape: {df.shape}, Dates: {df.index.min().date()} to {df.index.max().date()}"
    )

    param_grid = {
        "vol_target": [0.002, 0.005],
        "target_atr_mult": [1.0, 1.5, 2.0],
        "stop_atr_mult": [1.0, 1.5],
    }

    print("\nParameter Grid for Optimization:")
    for k, v in param_grid.items():
        print(f"  {k}: {v}")

    print("\nRunning WFA...")
    wfa = WalkForwardAnalyzer(
        data=df,
        train_years=3,
        test_years=1,
        slippage_bps=args.slippage_bps,
        spread_bps=0.0,
    )

    oos_trades = wfa.run(param_grid)

    print("\n--- Walk-Forward Analysis Complete ---")
    if oos_trades.empty:
        print("No trades generated out-of-sample.")
    else:
        print(f"Total OOS Trades: {len(oos_trades)}")
        print(f"Total OOS Net PnL: {oos_trades['pl'].sum():.2f}")
        print("\nOOS Equity Curve (Cumulative PnL over time):")

        oos_trades["cumulative_pl"] = oos_trades["pl"].cumsum()
        print(
            oos_trades[
                ["entry_price", "exit_price", "pl", "cumulative_pl", "wfa_window"]
            ].head(10)
        )
        print("...")
        print(
            oos_trades[
                ["entry_price", "exit_price", "pl", "cumulative_pl", "wfa_window"]
            ].tail(10)
        )

        out_path = os.path.join(project_root, "output", "wfa_oos_results.csv")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        oos_trades.to_csv(out_path, index=False)
        print(f"\nSaved detailed OOS trades to {out_path}")


if __name__ == "__main__":
    main()
