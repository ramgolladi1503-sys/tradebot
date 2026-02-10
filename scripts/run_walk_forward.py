import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.walk_forward import run_walk_forward


def main():
    parser = argparse.ArgumentParser(description="Run rolling walk-forward evaluation.")
    parser.add_argument("--input", default="data/NIFTY_20260123.csv", help="Input CSV with OHLCV and timestamp column")
    parser.add_argument("--train-window-days", type=int, default=60)
    parser.add_argument("--test-window-days", type=int, default=10)
    parser.add_argument("--step-days", type=int, default=10)
    parser.add_argument("--starting-capital", type=float, default=100000.0)
    parser.add_argument("--output-dir", default="reports/walk_forward")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    historical = pd.read_csv(input_path)
    summary = run_walk_forward(
        historical_data=historical,
        train_window_days=args.train_window_days,
        test_window_days=args.test_window_days,
        step_days=args.step_days,
        starting_capital=args.starting_capital,
        output_dir=args.output_dir,
        write_outputs=True,
    )

    artifacts = summary.get("artifacts", {})
    print("Walk-forward complete")
    print(f"Windows: {summary['config']['window_count']}")
    print(f"Avg return: {summary['aggregate']['avg_return']:.6f}")
    print(f"Total trades: {summary['aggregate']['total_trades']}")
    if artifacts:
        print(f"JSON: {artifacts.get('json')}")
        print(f"CSV: {artifacts.get('csv')}")
    else:
        print(json.dumps(summary["aggregate"], indent=2))


if __name__ == "__main__":
    main()
