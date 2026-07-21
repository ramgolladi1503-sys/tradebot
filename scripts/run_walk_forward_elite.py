from __future__ import annotations

import argparse
import math
import multiprocessing as mp
import sys
from collections import Counter
from itertools import product
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from core.backtest_elite import EliteBacktestConfig, VectorizedBacktestEngine
from core.tearsheet import generate_tearsheet, print_tearsheet


Params = tuple[int, float, float, float, float, float]
Metrics = dict[str, object]


def default_parameter_grid() -> list[Params]:
    return list(
        product(
            [15],
            [1.5],
            [3.0, 4.0],
            [1.0],
            [0.0, 1.5, 2.0],
            [0.5, 1.0],
        )
    )


def _config_from_params(params: Params) -> EliteBacktestConfig:
    horizon, slippage_bps, target_atr, stop_atr, trail_activation, trail_distance = params
    return EliteBacktestConfig(
        research_mode="PROXY_RESEARCH",
        use_synth_chain=False,
        horizon=horizon,
        slippage_bps=slippage_bps,
        spread_bps=slippage_bps,
        target_atr_mult=target_atr,
        stop_atr_mult=stop_atr,
        allowed_time_start="09:15",
        allowed_time_end="15:30",
        trailing_stop_activation_mult=trail_activation,
        trailing_stop_trail_mult=trail_distance,
    )


def evaluate_params(args):
    """Evaluate one parameter set on exactly the supplied data slice."""
    data, horizon, sl_bps, target_atr, stop_atr, ts_act, ts_trail = args
    params: Params = (horizon, sl_bps, target_atr, stop_atr, ts_act, ts_trail)
    engine = VectorizedBacktestEngine(data, _config_from_params(params))
    results = engine.generate_signals_vectorized()
    if results.empty:
        return (*params, {"error": "No trades executed"})
    return (*params, generate_tearsheet(results))


def _evaluate_parameter_set(data: pd.DataFrame, params: Params) -> Metrics:
    result = evaluate_params((data, *params))
    return result[-1]


def _score_metrics(metrics: Metrics) -> float:
    if "error" in metrics:
        return -float("inf")
    expectancy = float(metrics.get("after_cost_expectancy", 0.0) or 0.0)
    profit_factor = float(metrics.get("profit_factor", 0.0) or 0.0)
    if math.isinf(profit_factor):
        profit_factor = 2.0
    return expectancy * profit_factor


def _select_best_params(
    train_data: pd.DataFrame,
    parameter_grid: Iterable[Params],
    *,
    workers: int | None = None,
) -> tuple[Params | None, float]:
    params_list = list(parameter_grid)
    tasks = [(train_data, *params) for params in params_list]
    if not tasks:
        return None, -float("inf")

    if workers == 1 or len(tasks) == 1:
        results = [evaluate_params(task) for task in tasks]
    else:
        pool_size = min(workers or mp.cpu_count(), len(tasks))
        with mp.Pool(pool_size) as pool:
            results = pool.map(evaluate_params, tasks)

    best_params: Params | None = None
    best_score = -float("inf")
    for horizon, sl_bps, target_atr, stop_atr, ts_act, ts_trail, metrics in results:
        score = _score_metrics(metrics)
        if score > best_score:
            best_score = score
            best_params = (
                horizon,
                sl_bps,
                target_atr,
                stop_atr,
                ts_act,
                ts_trail,
            )
    return best_params, best_score


def build_walk_forward_plan(
    data: pd.DataFrame,
    *,
    block_count: int = 6,
    minimum_block_rows: int = 10,
) -> dict[str, object]:
    """Build three rolling train/test folds plus one untouched final holdout.

    With six chronological blocks:
      - fold 1 trains on blocks 0-1 and tests on block 2;
      - fold 2 trains on blocks 1-2 and tests on block 3;
      - fold 3 trains on blocks 2-3 and tests on block 4;
      - block 5 (plus any remainder) is the final untouched holdout.
    """
    if block_count != 6:
        raise ValueError("the certified plan requires exactly six blocks")
    fold_size = len(data) // block_count
    if fold_size < minimum_block_rows:
        raise ValueError("data is too small for certified walk-forward blocks")

    folds: list[dict[str, object]] = []
    for fold_index in range(3):
        train_start = fold_index * fold_size
        train_end = train_start + (2 * fold_size)
        test_start = train_end
        test_end = test_start + fold_size
        folds.append(
            {
                "fold": fold_index + 1,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "train_data": data.iloc[train_start:train_end],
                "test_data": data.iloc[test_start:test_end],
            }
        )

    holdout_start = 5 * fold_size
    return {
        "fold_size": fold_size,
        "folds": folds,
        "holdout_start": holdout_start,
        "holdout_data": data.iloc[holdout_start:],
    }


def _should_promote(
    *,
    final_holdout_metrics: Metrics,
    fold_reports: list[dict[str, object]],
    stability_penalty: int,
) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    holdout_pf = float(final_holdout_metrics.get("profit_factor", 0.0) or 0.0)
    holdout_expectancy = float(
        final_holdout_metrics.get("after_cost_expectancy", 0.0) or 0.0
    )
    if holdout_pf <= 1.2:
        blockers.append("FINAL_HOLDOUT_PROFIT_FACTOR_NOT_MET")
    if holdout_expectancy <= 0:
        blockers.append("FINAL_HOLDOUT_EXPECTANCY_NOT_MET")
    if stability_penalty > 2:
        blockers.append("PARAMETER_STABILITY_NOT_MET")

    positive_fold_expectancy = sum(
        1
        for report in fold_reports
        if float(report["test_metrics"].get("after_cost_expectancy", 0.0) or 0.0)
        > 0
    )
    required_positive_folds = math.ceil(len(fold_reports) / 2)
    if positive_fold_expectancy < required_positive_folds:
        blockers.append("WALK_FORWARD_FOLD_MAJORITY_NOT_MET")

    return not blockers, blockers


def run_walk_forward(
    data: pd.DataFrame,
    *,
    parameter_grid: Iterable[Params] | None = None,
    workers: int | None = None,
    select_fn: Callable[[pd.DataFrame, Iterable[Params]], tuple[Params | None, float]]
    | None = None,
    evaluate_fn: Callable[[pd.DataFrame, Params], Metrics] | None = None,
) -> dict[str, object]:
    """Run train-only selection, fold OOS evaluation and final holdout validation."""
    plan = build_walk_forward_plan(data)
    grid = (
        default_parameter_grid()
        if parameter_grid is None
        else list(parameter_grid)
    )
    if not grid:
        return {
            "status": "REJECTED",
            "promoted": False,
            "blockers": ["EMPTY_PARAMETER_GRID"],
            "fold_reports": [],
        }
    evaluator = evaluate_fn or _evaluate_parameter_set

    if select_fn is None:
        selector = lambda train, values: _select_best_params(
            train, values, workers=workers
        )
    else:
        selector = select_fn

    fold_reports: list[dict[str, object]] = []
    chosen_params: list[Params] = []
    for fold in plan["folds"]:
        train_data = fold["train_data"]
        test_data = fold["test_data"]
        best_params, train_score = selector(train_data, grid)
        if best_params is None:
            fold_reports.append(
                {
                    "fold": fold["fold"],
                    "status": "NO_VALID_PARAMETERS",
                    "train_start": fold["train_start"],
                    "train_end": fold["train_end"],
                    "test_start": fold["test_start"],
                    "test_end": fold["test_end"],
                }
            )
            continue

        test_metrics = evaluator(test_data, best_params)
        chosen_params.append(best_params)
        fold_reports.append(
            {
                "fold": fold["fold"],
                "status": "EVALUATED",
                "train_start": fold["train_start"],
                "train_end": fold["train_end"],
                "test_start": fold["test_start"],
                "test_end": fold["test_end"],
                "selected_params": best_params,
                "train_score": train_score,
                "test_metrics": test_metrics,
            }
        )

    evaluated_folds = [r for r in fold_reports if r["status"] == "EVALUATED"]
    if not chosen_params or not evaluated_folds:
        return {
            "status": "REJECTED",
            "promoted": False,
            "blockers": ["NO_VALID_WALK_FORWARD_FOLDS"],
            "fold_reports": fold_reports,
        }

    stability_penalty = len(set(chosen_params))
    final_params = Counter(chosen_params).most_common(1)[0][0]
    holdout_data = plan["holdout_data"]
    final_holdout_metrics = evaluator(holdout_data, final_params)
    if "error" in final_holdout_metrics:
        return {
            "status": "REJECTED",
            "promoted": False,
            "blockers": ["FINAL_HOLDOUT_HAS_NO_TRADES"],
            "fold_reports": fold_reports,
            "selected_params": final_params,
            "stability_penalty": stability_penalty,
        }

    promoted, blockers = _should_promote(
        final_holdout_metrics=final_holdout_metrics,
        fold_reports=evaluated_folds,
        stability_penalty=stability_penalty,
    )
    report = {
        "status": "PROMOTED" if promoted else "REJECTED",
        "promoted": promoted,
        "blockers": blockers,
        "fold_size": plan["fold_size"],
        "fold_reports": fold_reports,
        "selected_params": final_params,
        "stability_penalty": stability_penalty,
        "holdout_start": plan["holdout_start"],
        "holdout_metrics": final_holdout_metrics,
    }

    print("\n--- CERTIFIED WALK-FORWARD RESULT ---")
    print(f"Selected parameters: {final_params}")
    print(f"Stability penalty: {stability_penalty}")
    print_tearsheet(final_holdout_metrics)
    if promoted:
        print("PROMOTED: final holdout and fold-consistency gates passed.")
    else:
        print(f"REJECTED: {', '.join(blockers)}")
    return report


def run_option_backtest(csv_path: str) -> None:
    from core.option_backtest.engine import OptionBacktestEngine
    from core.option_backtest.models import OptionBacktestConfig, ResearchMode

    print("\n--- Running Real Option Data Backtest ---")
    config = OptionBacktestConfig(
        symbol="NIFTY",
        data_path=Path(csv_path),
        research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
        output_dir=Path("./options_output"),
    )
    result = OptionBacktestEngine(config).run()
    metrics = result.summary
    print("\n--- Option Backtest Tearsheet ---")
    for warning in metrics.get("warnings", []):
        print(f"\033[91m{warning}\033[0m")
    print(f"Total Signals:      {metrics.get('signals_total', 0)}")
    print(f"Executable Signals: {metrics.get('executable_signals', 0)}")
    print(f"Trades Taken:       {metrics.get('trades_taken', 0)}")
    print(f"Expectancy (Net):   ${metrics.get('after_cost_expectancy', 0):,.2f}")
    suffix = "" if metrics.get("after_cost_expectancy", 0) > 0 else " (IRRELEVANT)"
    print(f"Win Rate:           {metrics.get('win_rate', 0) * 100:.2f}%{suffix}")
    print(f"Profit Factor:      {metrics.get('profit_factor')}")
    print(f"Max Drawdown:       ${metrics.get('max_drawdown', 0):,.2f}")
    print(f"Total PnL:          ${metrics.get('total_pnl_value', 0):,.2f}")


def _load_csv(path: str) -> pd.DataFrame:
    data = pd.read_csv(path)
    if "close" not in data.columns and "close_price" in data.columns:
        data = data.rename(columns={"close_price": "close"})
    if "timestamp" in data.columns:
        timestamps = pd.to_datetime(data["timestamp"], errors="raise")
        data = data.copy()
        data.index = timestamps
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run certified walk-forward analysis")
    parser.add_argument("--csv", required=False, help="Path to walk-forward CSV data")
    parser.add_argument(
        "--use-options",
        action="store_true",
        help="Use OptionBacktestEngine instead of simulated futures",
    )
    args = parser.parse_args()

    if args.use_options:
        if not args.csv:
            print("Error: --csv is required when using --use-options")
            sys.exit(1)
        run_option_backtest(args.csv)
    elif args.csv:
        print(f"Loading data from {args.csv}...")
        run_walk_forward(_load_csv(args.csv))
    else:
        print("Generating synthetic data for a non-production smoke test...")
        dates = pd.date_range("2026-01-01", periods=1000, freq="min")
        smoke_data = pd.DataFrame(
            {
                "open": [100 + i * 0.1 for i in range(1000)],
                "close": [100 + i * 0.1 for i in range(1000)],
                "high": [101 + i * 0.1 for i in range(1000)],
                "low": [99 + i * 0.1 for i in range(1000)],
                "volume": [1000 for _ in range(1000)],
            },
            index=dates,
        )
        run_walk_forward(smoke_data)
