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
    data, horizon, sl_bps, target_atr, stop_atr, ts_act, ts_trail = args
    
    config = EliteBacktestConfig(
        research_mode="REAL_EXECUTABLE_RESEARCH",
        use_synth_chain=False,
        horizon=horizon,
        slippage_bps=sl_bps,
        spread_bps=sl_bps,
        target_atr_mult=target_atr,
        stop_atr_mult=stop_atr,
        allowed_time_start="09:15",
        allowed_time_end="15:30",
        trailing_stop_activation_mult=ts_act,
        trailing_stop_trail_mult=ts_trail
    )
    
    engine = VectorizedBacktestEngine(data, config)
    
    # Run the fast vectorized engine
    results = engine.generate_signals_vectorized()
    
    if results.empty:
        return (horizon, sl_bps, target_atr, stop_atr, ts_act, ts_trail, {"error": "No trades executed"})
        
    metrics = generate_tearsheet(results)
    return (horizon, sl_bps, target_atr, stop_atr, ts_act, ts_trail, metrics)

def run_walk_forward(data: pd.DataFrame):
    """
    Performs Walk-Forward Optimization (WFO):
    1. Splits data into In-Sample (IS) and Out-of-Sample (OOS).
    2. Runs grid search on IS.
    3. Evaluates best IS params on full data (IS + OOS).
    4. Applies robust promotion logic.
    """
    if len(data) < 100:
        print("Not enough data for walk forward.")
        return

    # Split 70% Train, 30% Test
    split_idx = int(len(data) * 0.7)
    train_data = data.iloc[:split_idx]
    test_data = data.iloc[split_idx:]
    
    try:
        oos_start_date = str(test_data.index[0])
    except Exception:
        oos_start_date = None

    horizons = [15]
    slippage_bps = [1.5]
    target_atrs = [3.0, 4.0]
    stop_atrs = [1.0]
    ts_act_mults = [0.0, 1.5, 2.0]
    ts_trail_mults = [0.5, 1.0]
    
    param_grid = list(product(horizons, slippage_bps, target_atrs, stop_atrs, ts_act_mults, ts_trail_mults))
    tasks_is = [(train_data, hz, sl, tgt, stp, ts_act, ts_trail) for hz, sl, tgt, stp, ts_act, ts_trail in param_grid]
    
    print(f"Starting Elite IS Grid Search for {len(param_grid)} permutations on {len(train_data)} rows...")
    start_time = time.time()
    
    with mp.Pool(mp.cpu_count()) as pool:
        results_is = pool.map(evaluate_params, tasks_is)
        
    end_time = time.time()
    print(f"IS Grid search completed in {end_time - start_time:.2f} seconds.")
    
    # Find the best Sortino ratio in IS
    best_params = None
    best_sortino = -float('inf')
    
    for hz, sl, tgt, stp, ts_act, ts_trail, metrics in results_is:
        if "error" in metrics:
            continue
        sortino = metrics.get("sortino_ratio_per_trade", 0)
        if sortino > best_sortino:
            best_sortino = sortino
            best_params = (hz, sl, tgt, stp, ts_act, ts_trail)
            
    if not best_params:
        print("No profitable parameters found in In-Sample data. Strategy Rejected.")
        return
        
    print(f"\nBest IS Parameters: Horizon={best_params[0]}, Slippage={best_params[1]} bps, Target ATR={best_params[2]}x, Stop ATR={best_params[3]}x, TS Act={best_params[4]}x, TS Trail={best_params[5]}x")
    
    # Run OOS Validation
    print(f"\nRunning Out-Of-Sample Validation starting from {oos_start_date}...")
    
    config = EliteBacktestConfig(
        research_mode="REAL_EXECUTABLE_RESEARCH",
        use_synth_chain=False,
        horizon=best_params[0],
        slippage_bps=best_params[1],
        spread_bps=best_params[1],
        target_atr_mult=best_params[2],
        stop_atr_mult=best_params[3],
        allowed_time_start="09:15",
        allowed_time_end="15:30",
        trailing_stop_activation_mult=best_params[4],
        trailing_stop_trail_mult=best_params[5],
        oos_start_date=oos_start_date
    )
    
    engine = VectorizedBacktestEngine(data, config)
    results_full = engine.generate_signals_vectorized()
    
    if results_full.empty:
        print("No trades executed in OOS run. Strategy Rejected.")
        return
        
    metrics = generate_tearsheet(results_full)
    print_tearsheet(metrics)
    
    pf_oos = metrics.get("profit_factor_oos", 0) or 0.0
    expectancy = metrics.get("after_cost_expectancy", 0)
    
    print("\n--- WALK FORWARD PROMOTION CHECK ---")
    if pf_oos > 1.2 and expectancy > 0:
        print(f"PROMOTED! Strategy meets elite robustness criteria (OOS PF: {pf_oos:.2f} > 1.2, Expectancy: {expectancy:.2f} > 0).")
    else:
        print(f"REJECTED. Failed robustness check (OOS PF: {pf_oos:.2f}, Expectancy: {expectancy:.2f}).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Elite Grid Search")
    parser.add_argument("--csv", required=False, help="Path to walk-forward CSV data")
    args = parser.parse_args()
    
    if args.csv:
        print(f"Loading data from {args.csv}...")
        data = pd.read_csv(args.csv)
        if "close" not in data.columns and "close_price" in data.columns:
            data = data.rename(columns={"close_price": "close"})
        run_walk_forward(data)
    else:
        # Dummy data generation for testing the script standalone
        print("Generating synthetic data for elite module test...")
        dates = pd.date_range("2026-01-01", periods=1000, freq="min")
        data = pd.DataFrame({
            "close": [100 + i * 0.1 for i in range(1000)],
            "high": [101 + i * 0.1 for i in range(1000)],
            "low": [99 + i * 0.1 for i in range(1000)],
            "volume": [1000 for _ in range(1000)]
        }, index=dates)
        run_walk_forward(data)
