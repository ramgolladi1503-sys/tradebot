from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import argparse

from core.model_registry import (
    activate_model,
    append_rejection_ledger,
    build_admission_report,
    get_active_entry,
    write_admission_report,
    write_rejection_artifact,
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, help="xgb/deep/micro")
    parser.add_argument("--path", required=True)
    parser.add_argument("--min-profit-factor", type=float, default=None)
    parser.add_argument("--min-expectancy", type=float, default=None)
    parser.add_argument("--max-drawdown", type=float, default=None, help="Negative floor for max drawdown")
    args = parser.parse_args()

    entry = get_active_entry(args.type) or {}
    governance = entry.get("governance") or {"features": ["manual_metric_only"], "training_window": {"rows": 0}, "walk_forward": {"status": "SELECTED", "selection": {"status": "SELECTED"}}}
    governance = dict(governance)
    if args.min_profit_factor is not None:
        governance["min_profit_factor"] = args.min_profit_factor
    if args.min_expectancy is not None:
        governance["min_expectancy"] = args.min_expectancy
    if args.max_drawdown is not None:
        governance["max_drawdown"] = args.max_drawdown
    profitability = {
        "expectancy": (entry.get("metrics") or {}).get("expectancy"),
        "profit_factor": (entry.get("metrics") or {}).get("profit_factor"),
        "max_drawdown": (entry.get("metrics") or {}).get("max_drawdown"),
        "net_pnl": (entry.get("metrics") or {}).get("net_pnl"),
        "win_rate": (entry.get("metrics") or {}).get("win_rate"),
    }
    profitability = {k: v for k, v in profitability.items() if v is not None}
    if profitability:
        governance["profitability"] = profitability
    admission = build_admission_report(
        model_type=args.type,
        path=args.path,
        status="active",
        governance=governance,
        metrics=entry.get("metrics") or {},
        checks={"cli": True},
    )
    if not admission["admitted"]:
        out = write_rejection_artifact(admission)
        append_rejection_ledger(admission)
        print({"rejected": True, "report_path": str(out), "report": admission})
        raise SystemExit(2)
    active = activate_model(args.type, args.path, governance=governance, metrics=entry.get("metrics") or {})
    out = write_admission_report(admission)
    print({"active": active, "admission_report_path": str(out), "admission_report": admission})
