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


def _session_blocks(
    sessions: pd.DatetimeIndex,
    *,
    block_count: int,
) -> list[pd.DatetimeIndex]:
    base_size, remainder = divmod(len(sessions), block_count)
    blocks: list[pd.DatetimeIndex] = []
    cursor = 0
    for block_index in range(block_count):
        size = base_size + (1 if block_index < remainder else 0)
        blocks.append(sessions[cursor : cursor + size])
        cursor += size
    return blocks


def _row_bounds(mask: pd.Series) -> tuple[int, int]:
    positions = [index for index, selected in enumerate(mask.to_numpy()) if selected]
    if not positions:
        raise ValueError("walk-forward session block produced no rows")
    return positions[0], positions[-1] + 1


def build_walk_forward_plan(
    data: pd.DataFrame,
    *,
    block_count: int = 6,
    minimum_block_sessions: int = 5,
) -> dict[str, object]:
    """Build whole-session rolling folds and one untouched final holdout.

    With six chronological session blocks:
      - fold 1 trains on blocks 0-1 and tests on block 2;
      - fold 2 trains on blocks 1-2 and tests on block 3;
      - fold 3 trains on blocks 2-3 and tests on block 4;
      - block 5 is the final untouched holdout.

    No trading session may appear in more than one lane of the same fold.
    """
    if block_count != 6:
        raise ValueError("the certified plan requires exactly six blocks")
    if minimum_block_sessions <= 0:
        raise ValueError("minimum_block_sessions must be positive")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("certified walk-forward data must use a DatetimeIndex")
    if data.index.hasnans:
        raise ValueError("walk-forward index contains invalid timestamps")
    if not data.index.is_monotonic_increasing:
        raise ValueError("walk-forward data must be sorted chronologically")

    session_keys = pd.Series(data.index.normalize(), index=data.index)
    unique_sessions = pd.DatetimeIndex(session_keys.drop_duplicates().to_list())
    required_sessions = block_count * minimum_block_sessions
    if len(unique_sessions) < required_sessions:
        raise ValueError(
            "data is too small for certified whole-session walk-forward blocks"
        )

    blocks = _session_blocks(unique_sessions, block_count=block_count)
    if any(len(block) < minimum_block_sessions for block in blocks):
        raise ValueError(
            "data is too small for certified whole-session walk-forward blocks"
        )

    folds: list[dict[str, object]] = []
    for fold_index in range(3):
        train_sessions = blocks[fold_index].append(blocks[fold_index + 1])
        test_sessions = blocks[fold_index + 2]
        train_mask = session_keys.isin(train_sessions)
        test_mask = session_keys.isin(test_sessions)
        train_start, train_end = _row_bounds(train_mask)
        test_start, test_end = _row_bounds(test_mask)
        if set(train_sessions).intersection(test_sessions):
            raise AssertionError("walk-forward train and test sessions overlap")
        folds.append(
            {
                "fold": fold_index + 1,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "train_start_session": train_sessions[0].isoformat(),
                "train_end_session": train_sessions[-1].isoformat(),
                "test_start_session": test_sessions[0].isoformat(),
                "test_end_session": test_sessions[-1].isoformat(),
                "train_sessions": [value.isoformat() for value in train_sessions],
                "test_sessions": [value.isoformat() for value in test_sessions],
                "train_data": data.loc[train_mask.to_numpy()].copy(),
                "test_data": data.loc[test_mask.to_numpy()].copy(),
            }
        )

    holdout_sessions = blocks[5]
    holdout_mask = session_keys.isin(holdout_sessions)
    holdout_start, holdout_end = _row_bounds(holdout_mask)
    used_pre_holdout_sessions = blocks[0]
    for block in blocks[1:5]:
        used_pre_holdout_sessions = used_pre_holdout_sessions.append(block)
    if set(used_pre_holdout_sessions).intersection(holdout_sessions):
        raise AssertionError("final holdout sessions overlap walk-forward sessions")

    return {
        "block_session_counts": [len(block) for block in blocks],
        "total_sessions": len(unique_sessions),
        "folds": folds,
        "holdout_start": holdout_start,
        "holdout_end": holdout_end,
        "holdout_start_session": holdout_sessions[0].isoformat(),
        "holdout_end_session": holdout_sessions[-1].isoformat(),
        "holdout_sessions": [value.isoformat() for value in holdout_sessions],
        "holdout_data": data.loc[holdout_mask.to_numpy()].copy(),
    }


def _should_promote(
    *,
    final_holdout_metrics: Metrics,
    fold_reports: list[dict[str, object]],
    stability_penalty: int,
) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if len(fold_reports) != 3:
        blockers.append("INCOMPLETE_WALK_FORWARD_FOLDS")

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


def _fold_report_base(fold: dict[str, object]) -> dict[str, object]:
    return {
        "fold": fold["fold"],
        "train_start": fold["train_start"],
        "train_end": fold["train_end"],
        "test_start": fold["test_start"],
        "test_end": fold["test_end"],
        "train_start_session": fold["train_start_session"],
        "train_end_session": fold["train_end_session"],
        "test_start_session": fold["test_start_session"],
        "test_end_session": fold["test_end_session"],
    }


def run_walk_forward(
    data: pd.DataFrame,
    *,
    parameter_grid: Iterable[Params] | None = None,
    workers: int | None = None,
    select_fn: Callable[[pd.DataFrame, Iterable[Params]], tuple[Params | None, float]]
    | None = None,
    evaluate_fn: Callable[[pd.DataFrame, Params], Metrics] | None = None,
) -> dict[str, object]:
    """Run train-only selection, all-fold OOS evaluation and final holdout validation."""
    plan = build_walk_forward_plan(data)
    grid = default_parameter_grid() if parameter_grid is None else list(parameter_grid)
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
        report_base = _fold_report_base(fold)
        if best_params is None:
            fold_reports.append(
                {
                    **report_base,
                    "status": "NO_VALID_PARAMETERS",
                }
            )
            continue

        test_metrics = evaluator(test_data, best_params)
        if "error" in test_metrics:
            fold_reports.append(
                {
                    **report_base,
                    "status": "TEST_METRICS_INVALID",
                    "selected_params": best_params,
                    "train_score": train_score,
                    "test_metrics": test_metrics,
                }
            )
            continue

        chosen_params.append(best_params)
        fold_reports.append(
            {
                **report_base,
                "status": "EVALUATED",
                "selected_params": best_params,
                "train_score": train_score,
                "test_metrics": test_metrics,
            }
        )

    evaluated_folds = [r for r in fold_reports if r["status"] == "EVALUATED"]
    if not evaluated_folds:
        return {
            "status": "REJECTED",
            "promoted": False,
            "blockers": ["NO_VALID_WALK_FORWARD_FOLDS"],
            "fold_reports": fold_reports,
        }
    if len(evaluated_folds) != len(plan["folds"]):
        return {
            "status": "REJECTED",
            "promoted": False,
            "blockers": ["INCOMPLETE_WALK_FORWARD_FOLDS"],
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
        "block_session_counts": plan["block_session_counts"],
        "total_sessions": plan["total_sessions"],
        "fold_reports": fold_reports,
        "selected_params": final_params,
        "stability_penalty": stability_penalty,
        "holdout_start": plan["holdout_start"],
        "holdout_end": plan["holdout_end"],
        "holdout_start_session": plan["holdout_start_session"],
        "holdout_end_session": plan["holdout_end_session"],
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


def _smoke_data() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    trading_days = pd.bdate_range("2026-01-01", periods=60)
    row_number = 0
    for day in trading_days:
        index = pd.date_range(
            day + pd.Timedelta(hours=9, minutes=15), periods=20, freq="5min"
        )
        values = [100.0 + (row_number + offset) * 0.1 for offset in range(len(index))]
        frames.append(
            pd.DataFrame(
                {
                    "open": values,
                    "close": values,
                    "high": [value + 1.0 for value in values],
                    "low": [value - 1.0 for value in values],
                    "volume": 1000,
                },
                index=index,
            )
        )
        row_number += len(index)
    return pd.concat(frames)


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
        print("Generating multi-session data for a non-production smoke test...")
        run_walk_forward(_smoke_data())
