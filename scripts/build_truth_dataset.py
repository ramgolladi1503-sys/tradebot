import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from ml.truth_dataset import build_truth_dataset


def _missingness_report(df: pd.DataFrame) -> dict:
    report = {}
    for col in df.columns:
        miss = float(df[col].isna().mean())
        report[col] = miss
    return report


def main():
    parser = argparse.ArgumentParser(description="Build the canonical truth dataset from DecisionEvents.")
    parser.add_argument("--jsonl", default=getattr(cfg, "DECISION_LOG_PATH", "logs/decision_events.jsonl"), help="DecisionEvents JSONL path.")
    parser.add_argument("--sqlite", default=getattr(cfg, "TRADE_DB_PATH", "data/trades.db"), help="DecisionEvents SQLite path.")
    parser.add_argument("--out-parquet", default="data/truth_dataset.parquet", help="Output parquet path.")
    parser.add_argument("--out-csv", default="", help="Optional output CSV path.")
    args = parser.parse_args()

    out_csv = Path(args.out_csv) if args.out_csv else None
    df, report = build_truth_dataset(
        decision_jsonl=Path(args.jsonl),
        decision_sqlite=Path(args.sqlite),
        out_parquet=Path(args.out_parquet),
        out_csv=out_csv,
    )

    executed = int(((df["gatekeeper_allowed"] == 1) & (df["risk_allowed"] == 1)).sum()) if "gatekeeper_allowed" in df.columns else 0
    rejected = int(len(df) - executed)
    filled = int((df["filled_bool"] == 1).sum()) if "filled_bool" in df.columns else 0
    missed = int(executed - filled)
    miss_report = _missingness_report(df)

    leakage_count = int(report.get("leakage_count", 0))
    print(f"Total decisions: {len(df)}")
    print(f"Executed: {executed} | Rejected: {rejected}")
    print(f"Filled: {filled} | Missed: {missed}")
    print(f"Leakage count: {leakage_count}")
    print("Missingness report:")
    for k, v in miss_report.items():
        if v > 0:
            print(f"  {k}: {v:.2%}")

    if leakage_count > 0:
        raise SystemExit("Leakage check failed: outcome timestamps <= decision timestamps.")


if __name__ == "__main__":
    main()
