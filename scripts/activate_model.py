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
    args = parser.parse_args()

    entry = get_active_entry(args.type) or {}
    governance = entry.get("governance") or {"features": ["manual_metric_only"], "training_window": {"rows": 0}, "walk_forward": {"status": "SELECTED", "selection": {"status": "SELECTED"}}}
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
