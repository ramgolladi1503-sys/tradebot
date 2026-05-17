#!/usr/bin/env python3
"""Capture read-only opportunity diagnostics evidence.

This script wraps the PR #55 diagnostics module and writes a durable evidence
bundle for review. It does not call brokers, submit orders, change ranking,
change execution gates, tune trades, or touch depth subscriptions.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from core.opportunity_diagnostics import build_opportunity_diagnostics, load_candidate_rows
from core.paths import logs_dir as default_logs_dir

EVIDENCE_SCHEMA_VERSION = 1


def _resolve_output_dir(output_dir: str | Path | None, logs_dir: str | Path | None) -> Path:
    if output_dir is not None:
        return Path(output_dir).expanduser()
    if logs_dir is not None:
        return Path(logs_dir).expanduser() / "evidence"
    return default_logs_dir() / "evidence"


def _source_exists(source_path: str | None) -> bool:
    if not source_path:
        return False
    return Path(source_path).expanduser().exists()


def build_evidence_bundle(report: dict[str, Any], *, source_path: str | None) -> dict[str, Any]:
    """Wrap an opportunity diagnostics report with evidence metadata."""

    warnings = list(report.get("warnings") or [])
    row_count = int(report.get("row_count") or 0)
    source_available = _source_exists(source_path)
    if not source_available:
        warnings.append("source_file_not_available_in_environment")
    if row_count == 0:
        warnings.append("no_runtime_rows_captured")

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generated_epoch": time.time(),
        "read_only": True,
        "is_order_action": False,
        "source_path": source_path,
        "source_exists": source_available,
        "row_count": row_count,
        "diagnostic_report": report,
        "warnings": sorted(set(str(item) for item in warnings)),
        "next_action": _next_action(report, source_exists=source_available),
    }


def _next_action(report: dict[str, Any], *, source_exists: bool) -> str:
    row_count = int(report.get("row_count") or 0)
    if not source_exists or row_count == 0:
        return "capture_live_or_latest_runtime_suggestions_then_rerun_diagnostics"
    if report.get("ui_is_ranked_opportunity_view") is False:
        return "design_candidate_pool_and_ranking_contract_from_observed_gaps"
    if report.get("flat_confidence_detected") is True:
        return "inspect_confidence_calculation_before_ranking_changes"
    if int(report.get("recovered_fallback_count") or 0) > 0:
        return "enforce_fallback_visibility_before_any_executable_truth_work"
    return "review_report_and_decide_next_read_only_or_implementation_pr"


def render_markdown_summary(bundle: dict[str, Any]) -> str:
    report = dict(bundle.get("diagnostic_report") or {})
    lines = [
        "# Opportunity Diagnostics Evidence",
        "",
        "This evidence bundle is read-only. It does not call brokers, submit orders, change ranking, change execution gates, tune trades, or touch depth subscriptions.",
        "",
        "## Source",
        "",
        f"- Source path: `{bundle.get('source_path')}`",
        f"- Source exists: `{bundle.get('source_exists')}`",
        f"- Row count: `{bundle.get('row_count')}`",
        "",
        "## Key diagnostic fields",
        "",
        f"- Confidence min/max/mean/std: `{report.get('confidence_raw_min')}` / `{report.get('confidence_raw_max')}` / `{report.get('confidence_raw_mean')}` / `{report.get('confidence_raw_std')}`",
        f"- Flat confidence detected: `{report.get('flat_confidence_detected')}`",
        f"- BUY side ratio: `{report.get('buy_side_ratio')}`",
        f"- SELL side ratio: `{report.get('sell_side_ratio')}`",
        f"- Recovered fallback count: `{report.get('recovered_fallback_count')}`",
        f"- Executable count: `{report.get('executable_count')}`",
        f"- Queue-only count: `{report.get('queue_only_count')}`",
        f"- Advisory count: `{report.get('advisory_count')}`",
        f"- Rank field present: `{report.get('rank_field_present')}`",
        f"- Opportunity score present: `{report.get('opportunity_score_present')}`",
        f"- UI is ranked opportunity view: `{report.get('ui_is_ranked_opportunity_view')}`",
        "",
        "## Warnings",
        "",
    ]
    warnings = list(bundle.get("warnings") or [])
    if warnings:
        lines.extend(f"- `{warning}`" for warning in warnings)
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Next action",
            "",
            f"`{bundle.get('next_action')}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence_bundle(
    *,
    input_path: str | Path | None = None,
    logs_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    tail: int | None = 500,
) -> dict[str, Path]:
    rows, source = load_candidate_rows(input_path=input_path, logs_dir=logs_dir, tail=tail)
    report = build_opportunity_diagnostics(rows, source_path=source)
    bundle = build_evidence_bundle(report, source_path=source)

    out_dir = _resolve_output_dir(output_dir, logs_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "opportunity_diagnostics_evidence_latest.json"
    md_path = out_dir / "opportunity_diagnostics_evidence_summary.md"

    tmp_json = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp_md = md_path.with_suffix(md_path.suffix + ".tmp")
    tmp_json.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    tmp_json.replace(json_path)
    tmp_md.write_text(render_markdown_summary(bundle), encoding="utf-8")
    tmp_md.replace(md_path)
    return {"json": json_path, "markdown": md_path}


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture read-only opportunity diagnostics evidence")
    parser.add_argument("--input", default=None, help="Optional JSONL/JSON/CSV candidate export path")
    parser.add_argument("--logs-dir", default=None, help="Runtime logs directory; defaults to core.paths.logs_dir()")
    parser.add_argument("--output-dir", default=None, help="Evidence output directory")
    parser.add_argument("--tail", type=int, default=500, help="Number of JSONL rows to inspect")
    parser.add_argument("--print", action="store_true", help="Print written file paths as JSON")
    args = parser.parse_args()

    written = write_evidence_bundle(
        input_path=args.input,
        logs_dir=args.logs_dir,
        output_dir=args.output_dir,
        tail=args.tail,
    )
    payload = {key: str(value) for key, value in written.items()}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Wrote opportunity diagnostics evidence: {written['json']} and {written['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
