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
        research_mode="PROXY_RESEARCH",
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
    Performs Rolling Walk-Forward Optimization (WFO):
    """
    if len(data) < 100:
        print("Not enough data for walk forward.")
        return

    horizons = [15]
    slippage_bps = [1.5]
    target_atrs = [3.0, 4.0]
    stop_atrs = [1.0]
    ts_act_mults = [0.0, 1.5, 2.0]
    ts_trail_mults = [0.5, 1.0]
    
    param_grid = list(product(horizons, slippage_bps, target_atrs, stop_atrs, ts_act_mults, ts_trail_mults))
    
    fold_size = len(data) // 6
    if fold_size < 10:
        print("Data too small for rolling folds")
        return
        
    best_params_per_fold = []
    
    for fold in range(4):
        train_start = fold * fold_size
        train_end = train_start + fold_size * 2
        
        train_data = data.iloc[train_start:train_end]
        
        tasks_is = [(train_data, hz, sl, tgt, stp, ts_act, ts_trail) for hz, sl, tgt, stp, ts_act, ts_trail in param_grid]
        
        print(f"Starting Elite IS Grid Search for Fold {fold+1} ({len(train_data)} rows)...")
        with mp.Pool(mp.cpu_count()) as pool:
            results_is = pool.map(evaluate_params, tasks_is)
            
        best_is_score = -float('inf')
        best_is_params = None
        
        for hz, sl, tgt, stp, ts_act, ts_trail, metrics in results_is:
            if "error" in metrics:
                continue
            exp = metrics.get("after_cost_expectancy", 0)
            pf = metrics.get("profit_factor", 0)
            if pf == float('inf'):
                pf = 2.0
            score = exp * pf
            
            if score > best_is_score:
                best_is_score = score
                best_is_params = (hz, sl, tgt, stp, ts_act, ts_trail)
                
        if best_is_params:
            best_params_per_fold.append(best_is_params)
            
    if not best_params_per_fold:
        print("No profitable params found across folds. Strategy Rejected.")
        return
        
    stability_penalty = len(set(best_params_per_fold))
    print(f"\nParameter Stability Penalty: {stability_penalty} (unique param sets across {len(best_params_per_fold)} folds)")
    
    from collections import Counter
    final_params = Counter(best_params_per_fold).most_common(1)[0][0]
    print(f"Final Chosen Parameters: {final_params}")
    
    oos_start = 4 * fold_size
    test_data = data.iloc[oos_start:]
    try:
        oos_start_date = str(test_data.index[0])
    except Exception:
        oos_start_date = None
        
    print(f"\nRunning Final Out-Of-Sample Validation starting from {oos_start_date}...")
    
    config = EliteBacktestConfig(
        research_mode="PROXY_RESEARCH",
        use_synth_chain=False,
        horizon=final_params[0],
        slippage_bps=final_params[1],
        spread_bps=final_params[1],
        target_atr_mult=final_params[2],
        stop_atr_mult=final_params[3],
        allowed_time_start="09:15",
        allowed_time_end="15:30",
        trailing_stop_activation_mult=final_params[4],
        trailing_stop_trail_mult=final_params[5],
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
    if pf_oos > 1.2 and expectancy > 0 and stability_penalty <= 2:
        print(f"PROMOTED! Strategy meets elite robustness criteria (OOS PF: {pf_oos:.2f} > 1.2, Expectancy: {expectancy:.2f} > 0, Stability Penalty: {stability_penalty} <= 2).")
    else:
        print(f"REJECTED. Failed robustness check (OOS PF: {pf_oos:.2f}, Expectancy: {expectancy:.2f}, Stability Penalty: {stability_penalty}).")

def run_option_backtest(csv_path: str):
    from core.option_backtest.engine import OptionBacktestEngine
    from core.option_backtest.models import OptionBacktestConfig, ResearchMode
    from pathlib import Path
    
    print(f"\n--- Running Real Option Data Backtest ---")
    config = OptionBacktestConfig(
        symbol="NIFTY",
        data_path=Path(csv_path),
        research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
        output_dir=Path("./options_output")
    )
    
    engine = OptionBacktestEngine(config)
    result = engine.run()
    
    metrics = result.summary
    print("\n--- Option Backtest Tearsheet ---")
    if "warnings" in metrics:
        for w in metrics["warnings"]:
            print(f"\033[91m{w}\033[0m")
    
    print(f"Total Signals:      {metrics.get('signals_total', 0)}")
    print(f"Executable Signals: {metrics.get('executable_signals', 0)}")
    print(f"Trades Taken:       {metrics.get('trades_taken', 0)}")
    print(f"Expectancy (Net):   ${metrics.get('after_cost_expectancy', 0):,.2f}")
    if metrics.get('after_cost_expectancy', 0) > 0:
        print(f"Win Rate:           {metrics.get('win_rate', 0)*100:.2f}%")
    else:
        print(f"Win Rate:           {metrics.get('win_rate', 0)*100:.2f}% (IRRELEVANT)")
        
    print(f"Profit Factor:      {metrics.get('profit_factor')}")
    print(f"Max Drawdown:       ${metrics.get('max_drawdown', 0):,.2f}")
    print(f"Total PnL:          ${metrics.get('total_pnl_value', 0):,.2f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Elite Grid Search")
    parser.add_argument("--csv", required=False, help="Path to walk-forward CSV data")
    parser.add_argument("--use-options", action="store_true", help="Use OptionBacktestEngine instead of simulated futures")
    args = parser.parse_args()
    
    if args.use_options:
        if not args.csv:
            print("Error: --csv is required when using --use-options")
            sys.exit(1)
        run_option_backtest(args.csv)
    elif args.csv:
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
