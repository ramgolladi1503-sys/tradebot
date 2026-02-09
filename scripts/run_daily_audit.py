import argparse
import sys
from pathlib import Path
from core.time_utils import now_ist

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.truth_dataset import build_truth_dataset
from core.reports.daily_audit import build_daily_audit
from core.reports.execution_report import build_execution_report
from core.reports.decay_report import build_decay_report
from core.reports.rl_shadow_report import build_rl_shadow_report


def main():
    parser = argparse.ArgumentParser(description="Run daily audit reports.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD date (default: today).")
    parser.add_argument("--truth", default="data/truth_dataset.parquet", help="Truth dataset parquet path.")
    args = parser.parse_args()

    day = args.date or now_ist().strftime("%Y-%m-%d")
    truth_path = Path(args.truth)
    if not truth_path.exists():
        build_truth_dataset(out_parquet=truth_path)

    df = pd.read_parquet(truth_path)

    audit_path = Path(f"logs/daily_audit_{day}.json")
    exec_path = Path(f"logs/execution_report_{day}.json")
    decay_path = Path(f"logs/decay_report_{day}.json")
    rl_path = Path(f"logs/rl_shadow_report_{day}.json")

    build_daily_audit(df, day, audit_path)
    build_execution_report(df, day, exec_path)
    build_decay_report(day, decay_path)
    build_rl_shadow_report(df, day, rl_path)

    print(f"Daily audit: {audit_path}")
    print(f"Execution report: {exec_path}")
    print(f"Decay report: {decay_path}")
    print(f"RL shadow report: {rl_path}")


if __name__ == "__main__":
    main()
