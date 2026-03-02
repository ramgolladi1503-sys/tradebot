import argparse
from pathlib import Path
from core.paths import logs_dir, data_root

from ml.alpha_factory import run_alpha_factory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_alpha_factory(
        truth_path=data_root() / "truth_dataset.parquet",
        days=args.days,
        dry_run=args.dry_run,
        out_report=logs_dir() / "alpha_factory_report.json",
    )
    print(f"Alpha factory report: {result.report_path}")
    if result.model_path:
        print(f"Challenger model saved: {result.model_path}")
    else:
        print("Dry-run: no model saved")


if __name__ == "__main__":
    main()
