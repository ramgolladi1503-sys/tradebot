#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.feature_builder import add_indicators
from core.walk_forward import run_walk_forward


def run_engineered_walk_forward(
    *,
    input_csv: str | Path,
    output_dir: str | Path,
    train_window_days: int,
    test_window_days: int,
    step_days: int,
    use_ml_overlay: bool = False,
) -> dict:
    source = Path(input_csv).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"input_csv_not_found:{source}")
    frame = pd.read_csv(source)
    if "timestamp" not in frame.columns:
        raise ValueError("missing_required_columns:timestamp")
    engineered = add_indicators(frame)
    engineered["timestamp"] = pd.to_datetime(
        engineered["timestamp"], errors="coerce"
    )
    engineered = engineered.dropna(subset=["timestamp"]).reset_index(drop=True)
    return run_walk_forward(
        historical_data=engineered,
        train_window_days=train_window_days,
        test_window_days=test_window_days,
        step_days=step_days,
        output_dir=str(Path(output_dir).expanduser()),
        write_outputs=True,
        use_ml_overlay=use_ml_overlay,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run walk-forward on engineered historical candles."
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument(
        "--output-dir", default="reports/walk_forward_engineered"
    )
    parser.add_argument("--train-window-days", type=int, default=60)
    parser.add_argument("--test-window-days", type=int, default=10)
    parser.add_argument("--step-days", type=int, default=10)
    args = parser.parse_args(argv)
    summary = run_engineered_walk_forward(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        train_window_days=args.train_window_days,
        test_window_days=args.test_window_days,
        step_days=args.step_days,
    )
    print(
        f"windows={summary['config']['window_count']} avg_return={summary['aggregate']['avg_return']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
