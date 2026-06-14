import pandas as pd
import multiprocessing as mp
from itertools import product
from core.backtest_elite import VectorizedBacktestEngine, EliteBacktestConfig
from core.tearsheet import generate_tearsheet, print_tearsheet
import time

def evaluate_params(args):
    """
    Evaluates a specific parameter combination.
    """
    data, signals_df, entry_window, horizon, sl_bps = args
    
    config = EliteBacktestConfig(
        entry_window=entry_window,
        horizon=horizon,
        slippage_bps=sl_bps,
        spread_bps=sl_bps  # mirroring slippage to spread for simplicity in grid
    )
    
    engine = VectorizedBacktestEngine(data, config)
    
    # Run the fast vectorized engine
    results = engine.run_vectorized_signals(signals_df)
    
    if results.empty:
        return (entry_window, horizon, sl_bps, {"error": "No trades executed"})
        
    metrics = generate_tearsheet(results)
    return (entry_window, horizon, sl_bps, metrics)

def run_grid_search(data: pd.DataFrame, signals_df: pd.DataFrame):
    """
    Spawns multiple processes to evaluate backtest parameters concurrently.
    """
    entry_windows = [1, 3, 5]
    horizons = [5, 10, 15]
    slippage_bps = [3.0, 5.0, 8.0]
    
    param_grid = list(product(entry_windows, horizons, slippage_bps))
    tasks = [(data, signals_df, ew, hz, sl) for ew, hz, sl in param_grid]
    
    print(f"Starting Elite Grid Search for {len(param_grid)} permutations...")
    start_time = time.time()
    
    with mp.Pool(mp.cpu_count()) as pool:
        results = pool.map(evaluate_params, tasks)
        
    end_time = time.time()
    print(f"Grid search completed in {end_time - start_time:.2f} seconds.")
    
    # Find the best Sortino ratio
    best_params = None
    best_sortino = -float('inf')
    best_metrics = None
    
    for ew, hz, sl, metrics in results:
        if "error" in metrics:
            continue
        sortino = metrics.get("sortino_ratio_per_trade", 0)
        if sortino > best_sortino:
            best_sortino = sortino
            best_params = (ew, hz, sl)
            best_metrics = metrics
            
    if best_params:
        print(f"\nOptimal Parameters found: Entry Window={best_params[0]}, Horizon={best_params[1]}, Slippage={best_params[2]} bps")
        print_tearsheet(best_metrics)
    else:
        print("No profitable parameters found.")

if __name__ == "__main__":
    # Dummy data generation for testing the script standalone
    print("Generating synthetic data for elite module test...")
    dates = pd.date_range("2026-01-01", periods=1000, freq="1min")
    data = pd.DataFrame({
        "close": [100 + i * 0.1 for i in range(1000)],
        "high": [101 + i * 0.1 for i in range(1000)],
        "low": [99 + i * 0.1 for i in range(1000)],
        "volume": [1000 for _ in range(1000)]
    }, index=dates)
    
    # Dummy pre-computed signals
    signals = pd.DataFrame({
        "signal_side": ["BUY", "SELL", "BUY"] * 30,
        "entry_price": [100.5, 101.5, 102.5] * 30,
        "target": [102.0, 100.0, 104.0] * 30,
        "stop_loss": [99.0, 103.0, 101.0] * 30,
        "qty": [10, 10, 10] * 30,
        "lot_size": [50, 50, 50] * 30
    })
    
    run_grid_search(data, signals)
