#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.backtesting.data_catalog import (
    build_diagnostics_report,
    load_backtest_config,
    write_diagnostics_report,
)


def _render_summary(report: dict) -> str:
    lines = [
        f"phase_one_verdict: {report.get('phase_one_verdict')}",
        f"data_readiness_verdict: {report.get('data_readiness_verdict')}",
        f"data_readiness_score: {report.get('data_readiness_score')}",
        f"available_sources: {len(report.get('available_sources') or [])}",
        f"invalid_sources: {len(report.get('invalid_sources') or [])}",
        f"symbols: {', '.join(report.get('questions', {}).get('what_symbols_are_covered') or []) or 'NONE'}",
    ]
    date_window = report.get("questions", {}).get("what_dates_are_covered") or {}
    lines.append(
        f"date_coverage: {date_window.get('start_date')} -> {date_window.get('end_date')}"
    )
    for item in report.get("mode_feasibility") or []:
        mode = item.get("mode")
        feasible = item.get("feasible")
        reasons = ",".join(item.get("reasons") or []) or "OK"
        lines.append(f"{mode}: feasible={feasible} reasons={reasons}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect local historical data and report feasible backtest modes."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to JSON config for the backtesting data catalog.",
    )
    parser.add_argument(
        "--output", default="", help="Optional diagnostics JSON output path override."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit the full report JSON to stdout."
    )
    args = parser.parse_args(argv)

    config = load_backtest_config(args.config)
    report = build_diagnostics_report(config)
    target = (
        Path(args.output).expanduser()
        if args.output
        else config.diagnostics_output_path
    )
    out = write_diagnostics_report(report, target)
    readiness_out = write_diagnostics_report(report, config.readiness_output_path)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_summary(report))
        print(f"diagnostics_report: {out}")
        print(f"readiness_report: {readiness_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
