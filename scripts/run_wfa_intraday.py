import os
import glob
import pandas as pd
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("bootstrap.py")))

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
            # 2019+ data has an extra open_interest column, so we explicitly select 0-7
            df = pd.read_csv(
                f,
                names=[
                    "ticker",
                    "date",
                    "time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ],
                usecols=[0, 1, 2, 3, 4, 5, 6, 7],
            )
            dfs.append(df)
        except Exception as e:
            print(f"Error reading {f}: {e}")

    if not dfs:
        print("No data found!")
        return pd.DataFrame()

    print("Concatenating files...")
    combined = pd.concat(dfs, ignore_index=True)

    print("Formatting datetime...")
    combined["date_str"] = combined["date"].astype(str)
    combined["time_str"] = combined["time"].astype(str)
    # Some dates might be like '20130301', some might be '01-03-2013' or '2013-03-01'
    # We will try to parse with a unified format or coerce
    combined["datetime"] = pd.to_datetime(
        combined["date_str"] + " " + combined["time_str"], errors="coerce"
    )
    combined = combined.dropna(subset=["datetime"])
    combined.set_index("datetime", inplace=True)
    combined.sort_index(inplace=True)

    # Keep only OHLCV
    combined = combined[["open", "high", "low", "close", "volume"]].astype(float)

    # Filter to 2017-2022 to keep it manageable and clean (5 years)
    combined = combined.loc["2017-01-01":"2022-12-31"]

    # Resample to 5-minute to speed up analysis if 1-min is too noisy/slow, or just keep 1-min. Let's keep 5-min for realistic slippage.
    # Actually let's use 5-minute data to remove micro-noise.
    print("Resampling to 5-minute bars...")
    ohlc_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    combined = combined.resample("5min").agg(ohlc_dict).dropna()

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
        slippage_bps=5.0,  # Realistic NIFTY Futures slippage
        spread_bps=0.0,
    )

    # Expanded grid for Scalping Optimization (High Win Rate, Low R:R)
    param_grid = {
        "horizon": [75],
        "vol_target": [0.002],
        "target_atr_mult": [0.5, 0.75, 1.0],
        "stop_atr_mult": [1.5, 2.0],
        "allowed_time_end": ["10:30"],
        "trailing_stop_activation_mult": [0.0],
        "trailing_stop_trail_mult": [0.0],
    }

    print("\nStarting Intraday Walk-Forward Analysis (5-min timeframe)...")
    oos_trades = wfa.run(param_grid)

    if oos_trades.empty:
        print("\nNo OOS trades generated.")
        return

    print("\n--- WFA OOS Performance Summary (Intraday Real Data) ---")
    total_oos_pnl = oos_trades["pl"].sum()
    win_rate = (oos_trades["pl"] > 0).mean() * 100
    total_trades = len(oos_trades)

    print(f"Total OOS PnL (after 5 bps slippage): {total_oos_pnl:.2f}")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {win_rate:.2f}%")

    # Dump trades to CSV for ML Training
    from pathlib import Path

    csv_path = str(Path() / "data" / "oos_trades.csv")
    oos_trades.to_csv(csv_path, index=False)
    print(f"\nSaved {len(oos_trades)} trades to {csv_path} for ML Overlay training.")


if __name__ == "__main__":
    run_intraday_wfa()
