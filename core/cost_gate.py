from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from config import config as cfg
from core.cost_sensitivity import compute_cost_kpis, parse_execution_events, write_report
from core.events import events_path
from core.paths import logs_dir


def run_cost_gate(desk_id: str, *, events_path_override: Path | None = None) -> tuple[str, dict[str, Any]]:
    del desk_id  # Reserved for future desk-specific event partitioning.
    target_events = Path(events_path_override) if events_path_override is not None else events_path()
    trades = parse_execution_events(target_events)
    report = compute_cost_kpis(trades, cfg)
    out_json = logs_dir() / "cost_kpis.json"
    out_md = logs_dir() / "cost_kpis.md"
    write_report(report, out_json, out_md)

    details = {
        "status": str(report.status),
        "breaches": list(report.breaches),
        "totals": dict(report.totals),
        "thresholds": dict(report.thresholds),
        "events_path": str(target_events),
        "report_json_path": str(out_json),
        "report_md_path": str(out_md),
    }
    return (str(report.status), details)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run edge-after-costs readiness gate.")
    parser.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    parser.add_argument("--events-path", default=None)
    args = parser.parse_args(argv)

    status, details = run_cost_gate(
        str(args.desk),
        events_path_override=Path(args.events_path) if args.events_path else None,
    )
    print(f"COST_GATE: {status}")
    print(f"report_json: {details.get('report_json_path')}")
    print(f"report_md: {details.get('report_md_path')}")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
