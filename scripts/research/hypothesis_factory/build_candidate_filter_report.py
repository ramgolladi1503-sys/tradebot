#!/usr/bin/env python3
"""Build an auditable candidate filter report from a corpus screen run.

This script does not certify edge. It collapses duplicate hypothesis shapes and
explains why every screened candidate is rejected or allowed to proceed to
robustness validation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import strategy_certification_artifacts as sca  # noqa: E402


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.screen_run_dir)
    manifest_path = run_dir / "run_manifest.json"
    leaderboard_path = run_dir / "leaderboard.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing screen manifest: {manifest_path}")
    if not leaderboard_path.exists():
        raise FileNotFoundError(f"missing leaderboard: {leaderboard_path}")

    manifest = sca.read_json(manifest_path)
    rows = sca.read_csv(leaderboard_path)
    annotated = sca.annotate_candidates(
        rows,
        min_trades=args.min_trades,
        min_net_expectancy_bps=args.min_net_expectancy_bps,
        min_profit_factor=args.min_profit_factor,
        max_drawdown_bps_abs=args.max_drawdown_bps_abs,
    )
    summary = sca.summarize_annotations(annotated)

    report = {
        "schema_version": "tradebot-candidate-filter-report-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "screen_run_id": manifest.get("run_id"),
        "screen_run_dir": str(run_dir),
        "screen_manifest_sha256": sca.sha256_file(manifest_path),
        "leaderboard_sha256": sca.sha256_file(leaderboard_path),
        "runtime_authority": sca.SAFE_RUNTIME_AUTHORITY,
        "broker_actions_allowed": sca.SAFE_BROKER_ACTIONS_ALLOWED,
        "certification": sca.SAFE_CERTIFICATION,
        "thresholds": {
            "min_trades": args.min_trades,
            "min_net_expectancy_bps": args.min_net_expectancy_bps,
            "min_profit_factor": args.min_profit_factor,
            "max_drawdown_bps_abs": args.max_drawdown_bps_abs,
        },
        "summary": summary,
        "candidates": annotated,
    }

    out_dir = Path(args.output_dir) if args.output_dir else run_dir
    json_path = out_dir / "candidate_filter_report.json"
    md_path = out_dir / "candidate_filter_report.md"
    sca.write_json(json_path, report)

    lines = [
        f"- Screen run: `{report['screen_run_id']}`",
        f"- Candidates: `{summary['candidates']}`",
        f"- Unique shapes: `{summary['unique_shapes']}`",
        f"- Duplicates: `{summary['duplicates']}`",
        f"- Eligible for robustness: `{summary['eligible_for_robustness']}`",
        f"- Runtime authority: `{report['runtime_authority']}`",
        f"- Broker actions allowed: `{report['broker_actions_allowed']}`",
        "",
        "## Rejection Reason Counts",
        "",
        "```json",
        json.dumps(summary["rejection_reason_counts"], indent=2, sort_keys=True),
        "```",
        "",
        "## Eligible Candidates",
        "",
    ]
    eligible = [row for row in annotated if row.get("eligible_for_robustness")]
    if not eligible:
        lines.append("No candidates are eligible for robustness.")
    else:
        for row in eligible:
            lines.extend(
                [
                    f"### `{row['hypothesis_id']}`",
                    "",
                    f"- shape: `{row['candidate_shape_key']}`",
                    f"- instrument: `{row.get('instrument')}`",
                    f"- family: `{row.get('family')}`",
                    f"- direction: `{row.get('direction')}`",
                    f"- trades: `{row.get('trades')}`",
                    f"- win_rate: `{row.get('win_rate')}`",
                    f"- net_expectancy_bps: `{row.get('net_expectancy_bps')}`",
                    f"- profit_factor: `{row.get('profit_factor')}`",
                    f"- max_drawdown_bps: `{row.get('max_drawdown_bps')}`",
                    "",
                    "Verdict: `ROBUSTNESS_REQUIRED`.",
                    "",
                ]
            )
    sca.write_markdown_report(md_path, "Strategy Candidate Filter Report", lines)
    report["outputs"] = {
        "candidate_filter_report": str(json_path),
        "candidate_filter_report_md": str(md_path),
    }
    sca.write_json(json_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen-run-dir", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--min-net-expectancy-bps", type=float, default=0.0)
    parser.add_argument("--min-profit-factor", type=float, default=1.05)
    parser.add_argument("--max-drawdown-bps-abs", type=float, default=1000.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args)
    print(json.dumps({
        "screen_run_id": report["screen_run_id"],
        "candidates": report["summary"]["candidates"],
        "unique_shapes": report["summary"]["unique_shapes"],
        "eligible_for_robustness": report["summary"]["eligible_for_robustness"],
        "runtime_authority": report["runtime_authority"],
        "broker_actions_allowed": report["broker_actions_allowed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
