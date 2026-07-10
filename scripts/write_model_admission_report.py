from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import argparse

from core.model_registry import build_admission_report, write_admission_report, write_rejection_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a shared model admission report.")
    parser.add_argument("--type", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--status", default="candidate")
    parser.add_argument("--feature", action="append", default=[], help="Feature name; repeatable.")
    parser.add_argument("--train-rows", type=int, default=0)
    parser.add_argument("--regime-coverage", action="append", default=[], help="regime=share; repeatable.")
    parser.add_argument("--min-regime-coverage", type=float, default=0.2)
    parser.add_argument("--min-profit-factor", type=float, default=None)
    parser.add_argument("--min-expectancy", type=float, default=None)
    parser.add_argument("--max-drawdown", type=float, default=None, help="Negative floor for max drawdown")
    parser.add_argument("--reject-on-fail", action="store_true")
    args = parser.parse_args()

    regime_coverage = {}
    for item in args.regime_coverage:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        try:
            regime_coverage[key.strip()] = float(value)
        except Exception:
            continue

    governance = {
        "features": list(args.feature) or ["manual_metric_only"],
        "training_window": {"rows": int(args.train_rows), "start": None, "end": None},
        "regime_coverage": regime_coverage,
        "min_regime_coverage": float(args.min_regime_coverage),
        "min_profit_factor": args.min_profit_factor,
        "min_expectancy": args.min_expectancy,
        "max_drawdown": args.max_drawdown,
        "walk_forward": {"status": "SELECTED", "selection": {"status": "SELECTED"}},
    }
    report = build_admission_report(
        model_type=args.type,
        path=args.path,
        status=args.status,
        governance=governance,
        metrics={"train_rows": int(args.train_rows)},
        checks={"cli": True},
    )
    if not report["admitted"] and args.reject_on_fail:
        out = write_rejection_artifact(report)
        print({"rejected": True, "report_path": str(out), "report": report})
        return 2

    out = write_admission_report(report)
    print({"report_path": str(out), "report": report})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
