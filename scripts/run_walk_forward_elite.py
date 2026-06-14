import pandas as pd
import multiprocessing as mp
from itertools import product
from core.backtest_elite import VectorizedBacktestEngine, EliteBacktestConfig
from core.tearsheet import generate_tearsheet, print_tearsheet
import time
import argparse
import sys

def evaluate_params(args):
    """
    Evaluates a specific parameter combination.
    """
    data, horizon, sl_bps, target_atr, stop_atr = args
    
    config = EliteBacktestConfig(
        use_synth_chain=False,
        horizon=horizon,
        slippage_bps=sl_bps,
        spread_bps=sl_bps,  # mirroring slippage to spread for simplicity in grid
        target_atr_mult=target_atr,
        stop_atr_mult=stop_atr
    )
    
    engine = VectorizedBacktestEngine(data, config)
    
    # Run the fast vectorized engine
    results = engine.generate_signals_vectorized()
    
    if results.empty:
        return (horizon, sl_bps, target_atr, stop_atr, {"error": "No trades executed"})
        
    metrics = generate_tearsheet(results)
    return (horizon, sl_bps, target_atr, stop_atr, metrics)

def run_grid_search(data: pd.DataFrame):
    """
    Spawns multiple processes to evaluate backtest parameters concurrently.
    """
    horizons = [10, 15]
    slippage_bps = [0.5, 1.0, 1.5]
    target_atrs = [1.5, 2.5, 4.0]
    stop_atrs = [0.5, 1.0]
    
    param_grid = list(product(horizons, slippage_bps, target_atrs, stop_atrs))
    tasks = [(data, hz, sl, tgt, stp) for hz, sl, tgt, stp in param_grid]
    
    print(f"Starting Elite Grid Search for {len(param_grid)} permutations on {len(data)} rows...")
    start_time = time.time()
    
    with mp.Pool(mp.cpu_count()) as pool:
        results = pool.map(evaluate_params, tasks)
        
    end_time = time.time()
    print(f"Grid search completed in {end_time - start_time:.2f} seconds.")
    
    # Find the best Sortino ratio
    best_params = None
    best_sortino = -float('inf')
    best_metrics = None
    
    for hz, sl, tgt, stp, metrics in results:
        if "error" in metrics:
            continue
        sortino = metrics.get("sortino_ratio_per_trade", 0)
        if sortino > best_sortino:
            best_sortino = sortino
            best_params = (hz, sl, tgt, stp)
            best_metrics = metrics
            
    if best_params:
        print(f"\nOptimal Parameters found: Horizon={best_params[0]}, Slippage={best_params[1]} bps, Target ATR={best_params[2]}x, Stop ATR={best_params[3]}x")
        print_tearsheet(best_metrics)
    else:
        print("No profitable parameters found.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Elite Grid Search")
    parser.add_argument("--csv", required=False, help="Path to walk-forward CSV data")
    args = parser.parse_args()
    
    if args.csv:
        print(f"Loading data from {args.csv}...")
        data = pd.read_csv(args.csv)
        if "close" not in data.columns and "close_price" in data.columns:
            data = data.rename(columns={"close_price": "close"})
        run_grid_search(data)
    else:
        # Dummy data generation for testing the script standalone
        print("Generating synthetic data for elite module test...")
        dates = pd.date_range("2026-01-01", periods=1000, freq="1min")
        data = pd.DataFrame({
            "close": [100 + i * 0.1 for i in range(1000)],
            "high": [101 + i * 0.1 for i in range(1000)],
            "low": [99 + i * 0.1 for i in range(1000)],
            "volume": [1000 for _ in range(1000)]
        }, index=dates)
        run_grid_search(data)
