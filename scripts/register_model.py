from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import argparse

from core.model_registry import (
    admit_model_entry,
    append_rejection_ledger,
    build_admission_report,
    register_model,
    write_admission_report,
    write_rejection_artifact,
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, help="xgb/deep/micro")
    parser.add_argument("--path", required=True)
    parser.add_argument("--metric", action="append", default=[], help="key=value pairs")
    parser.add_argument("--min-profit-factor", type=float, default=None)
    parser.add_argument("--min-expectancy", type=float, default=None)
    parser.add_argument("--max-drawdown", type=float, default=None, help="Negative floor for max drawdown")
    args = parser.parse_args()

    metrics = {}
    for kv in args.metric:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                v = float(v)
            except Exception:
                pass
            metrics[k] = v
    profitability = {
        "expectancy": metrics.get("expectancy"),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown": metrics.get("max_drawdown"),
        "net_pnl": metrics.get("net_pnl"),
        "win_rate": metrics.get("win_rate"),
    }
    profitability = {k: v for k, v in profitability.items() if v is not None}
    governance = {
        "features": list(metrics.keys()) or ["manual_metric_only"],
        "training_window": {"rows": int(metrics.get("train_rows", 0) or 0), "start": None, "end": None},
        "regime_coverage": metrics.get("regime_coverage") if isinstance(metrics.get("regime_coverage"), dict) else {},
        "min_regime_coverage": 0.2,
        "min_profit_factor": args.min_profit_factor,
        "min_expectancy": args.min_expectancy,
        "max_drawdown": args.max_drawdown,
        "walk_forward": {"status": "SELECTED", "selection": {"status": "SELECTED"}},
    }
    if profitability:
        governance["profitability"] = profitability
    admission = build_admission_report(
        model_type=args.type,
        path=args.path,
        status="candidate",
        governance=governance,
        metrics=metrics,
        checks={"cli": True},
    )
    if not admission["admitted"]:
        out = write_rejection_artifact(admission)
        append_rejection_ledger(admission)
        print({"rejected": True, "report_path": str(out), "report": admission})
        raise SystemExit(2)
    admit_model_entry(
        {
            "type": args.type,
            "path": args.path,
            "hash": admission["hash"],
            "governance": governance,
        }
    )
    entry = register_model(args.type, args.path, metrics=metrics, governance=governance)
    out = write_admission_report(admission)
    print({"entry": entry, "admission_report_path": str(out), "admission_report": admission})
