import pandas as pd
from core.backtest_elite import VectorizedBacktestEngine, EliteBacktestConfig
from core.tearsheet import generate_tearsheet, print_tearsheet
import time
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to walk-forward CSV data")
    args = parser.parse_args()
    
    print(f"Loading data from {args.csv}...")
    data = pd.read_csv(args.csv)
    # Ensure necessary columns
    if "close" not in data.columns and "close_price" in data.columns:
        data = data.rename(columns={"close_price": "close"})
        
    print(f"Loaded {len(data)} rows. Initiating Elite Backtester generation...")
    
    config = EliteBacktestConfig(
        use_synth_chain=False, # Disable synthetic chains for speed over 5 years
        entry_window=3,
        horizon=15,
        slippage_bps=5.0
    )
    engine = VectorizedBacktestEngine(data, config)
    
    start = time.time()
    results = engine.generate_signals_vectorized()
    end = time.time()
    
    print(f"Signal Generation and Vectorized Execution finished in {end - start:.2f} seconds.")
    
    if results.empty:
        print("No trades were generated or executed.")
        return
        
    metrics = generate_tearsheet(results)
    print_tearsheet(metrics)

if __name__ == "__main__":
    main()
