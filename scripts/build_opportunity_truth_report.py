#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.validate_candidate_truth import build_truth_report


DEFAULT_SOURCES = [
    "logs/review_queue.json",
    "logs/quick_review_queue.json",
    "logs/approved_trades.json",
    "logs/advisory_rows.json",
    "runtime/review_queue.json",
    "runtime/quick_review_queue.json",
]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_candidates(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in (
            "candidates",
            "trades",
            "items",
            "rows",
            "review_queue",
            "approved_trades",
            "top_executable_candidates",
            "advisory_candidates",
            "near_executable_candidates",
            "rejected_candidates",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        if any(key in payload for key in ("trade_id", "symbol", "instrument_id", "tradingsymbol")):
            return [dict(payload)]
    return []


def _candidate_key(candidate: dict[str, Any], fallback: str) -> str:
    return str(
        candidate.get("trade_id")
        or candidate.get("candidate_id")
        or candidate.get("trade_key")
        or candidate.get("instrument_id")
        or candidate.get("tradingsymbol")
        or fallback
    )


def _merge_candidates_by_key(sources: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged: dict[str, dict[str, Any]] = {}
    loaded_sources: list[dict[str, Any]] = []
    for source in sources:
        if not source.exists():
            loaded_sources.append({"path": str(source), "exists": False, "candidate_count": 0})
            continue
        payload = _load_json(source)
        candidates = _extract_candidates(payload)
        loaded_sources.append({"path": str(source), "exists": True, "candidate_count": len(candidates)})
        for index, candidate in enumerate(candidates):
            key = _candidate_key(candidate, f"{source}:{index}")
            existing = merged.get(key, {})
            combined = dict(existing)
            combined.update(candidate)
            source_paths = list(combined.get("truth_report_sources") or [])
            if str(source) not in source_paths:
                source_paths.append(str(source))
            combined["truth_report_sources"] = source_paths
            merged[key] = combined
    return list(merged.values()), loaded_sources


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Opportunity Truth Report")
    lines.append("")
    lines.append("This is a non-wired multi-source report. It does not modify queues, trades, approvals, or runtime state.")
    lines.append("")
    lines.append("## Source Files")
    lines.append("")
    for row in report.get("loaded_sources", []):
        status = "found" if row.get("exists") else "missing"
        lines.append(f"- `{row['path']}` — {status}, candidates={row.get('candidate_count', 0)}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key, value in report["truth_report"]["summary"].items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    lines.append("## Candidate Pool Counts")
    lines.append("")
    for key, value in report["truth_report"].get("candidate_pool_counts", {}).items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    lines.append("## Dirty Selected / Executable Candidates")
    lines.append("")
    dirty = report["truth_report"].get("dirty_selected_candidates", [])
    if not dirty:
        lines.append("No dirty selected/executable candidates detected.")
    else:
        for row in dirty:
            blockers = ", ".join(row.get("execution_truth_blockers") or []) or "none"
            lines.append(f"- `{row.get('ref')}` symbol={row.get('symbol')} grade={row.get('data_quality_grade')} blockers={blockers}")
    lines.append("")
    lines.append("## Top Blockers")
    lines.append("")
    blockers = report["truth_report"].get("blocker_distribution", {})
    if isinstance(blockers, dict):
        for blocker, count in sorted(blockers.items(), key=lambda item: (-int(item[1]), item[0]))[:25]:
            lines.append(f"- {blocker}: {count}")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build non-wired multi-source opportunity truth report")
    parser.add_argument("--inputs", nargs="*", default=None, help="Input JSON files. Defaults to common logs/runtime files.")
    parser.add_argument("--out-json", default="logs/opportunity_truth_report.json")
    parser.add_argument("--out-md", default="logs/opportunity_truth_report.md")
    parser.add_argument("--fail-on-dirty-selected", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sources = [Path(raw) for raw in (args.inputs if args.inputs else DEFAULT_SOURCES)]
    candidates, loaded_sources = _merge_candidates_by_key(sources)
    truth_report = build_truth_report(candidates, source="multi-source")
    payload = {
        "loaded_sources": loaded_sources,
        "candidate_count_after_merge": len(candidates),
        "truth_report": truth_report,
    }
    _write_json(Path(args.out_json), payload)
    _write_markdown(Path(args.out_md), payload)
    if args.print_summary:
        print(json.dumps(truth_report["summary"], indent=2, sort_keys=True))
    dirty_count = int(truth_report["summary"].get("dirty_selected_or_executable", 0) or 0)
    return 1 if args.fail_on_dirty_selected and dirty_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
