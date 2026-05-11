#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from core.candidate_pool import build_candidate_pool
from core.data_quality import assess_candidate_data_quality
from core.paths import logs_dir


DEFAULT_INPUT_CANDIDATES = (
    str(logs_dir() / "review_queue.json"),
    str(logs_dir() / "quick_review_queue.json"),
    str(logs_dir() / "approved_trades.json"),
    str(logs_dir() / "advisory_rows.json"),
    "runtime/review_queue.json",
    "runtime/quick_review_queue.json",
)


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
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        if any(key in payload for key in ("trade_id", "symbol", "instrument_id", "tradingsymbol")):
            return [dict(payload)]
    return []


def _candidate_ref(candidate: dict[str, Any], index: int) -> str:
    return str(
        candidate.get("trade_id")
        or candidate.get("candidate_id")
        or candidate.get("instrument_id")
        or candidate.get("tradingsymbol")
        or candidate.get("symbol")
        or f"candidate-{index}"
    )


def _looks_execution_selected(candidate: dict[str, Any]) -> bool:
    permission = str(candidate.get("permission") or "").strip().upper()
    final_action = str(candidate.get("final_action") or "").strip().upper()
    execution_status = str(candidate.get("execution_status") or "").strip().lower()
    return bool(
        candidate.get("selected_for_execution")
        or candidate.get("is_executable")
        or candidate.get("eligible_for_execution")
        or (permission == "EXECUTE" and final_action == "EXECUTE")
        or execution_status == "executable"
    )


def _audit_candidate(candidate: dict[str, Any], index: int) -> dict[str, Any]:
    result = assess_candidate_data_quality(candidate)
    selected = _looks_execution_selected(candidate)
    dirty_selected = bool(selected and not result.execution_truth_allowed)
    return {
        "index": index,
        "ref": _candidate_ref(candidate, index),
        "symbol": candidate.get("symbol") or candidate.get("underlying"),
        "selected_or_executable_hint": selected,
        "dirty_selected": dirty_selected,
        "data_quality_grade": result.data_quality_grade,
        "execution_truth_allowed": result.execution_truth_allowed,
        "execution_truth_blockers": result.execution_truth_blockers,
        "fallback_fields": result.fallback_fields,
        "data_lineage": result.lineage,
        "final_score": candidate.get("final_score") or candidate.get("rank_score") or candidate.get("opportunity_score"),
        "candidate_status": candidate.get("candidate_status"),
        "execution_status": candidate.get("execution_status"),
        "permission": candidate.get("permission"),
        "final_action": candidate.get("final_action"),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Candidate Truth Validation Report")
    lines.append("")
    lines.append("This report is non-wired. It reads existing candidate/trade outputs and does not change live bot behavior.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key, value in report["summary"].items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    lines.append("## Grade Distribution")
    lines.append("")
    for grade, count in sorted(report["grade_distribution"].items()):
        lines.append(f"- {grade}: {count}")
    lines.append("")
    lines.append("## Top Blockers")
    lines.append("")
    for blocker, count in report["blocker_distribution"].most_common(20):
        lines.append(f"- {blocker}: {count}")
    lines.append("")
    lines.append("## Dirty Selected / Executable Candidates")
    lines.append("")
    dirty = report["dirty_selected_candidates"]
    if not dirty:
        lines.append("No dirty selected/executable candidates detected.")
    else:
        for row in dirty:
            blockers = ", ".join(row.get("execution_truth_blockers") or []) or "none"
            lines.append(
                f"- `{row['ref']}` symbol={row.get('symbol')} grade={row.get('data_quality_grade')} blockers={blockers}"
            )
    lines.append("")
    lines.append("## Candidate Pool Counts")
    lines.append("")
    for key, value in report["candidate_pool_counts"].items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_truth_report(candidates: list[dict[str, Any]], *, source: str) -> dict[str, Any]:
    audited = [_audit_candidate(candidate, index) for index, candidate in enumerate(candidates)]
    pool = build_candidate_pool(candidates)
    grade_distribution = Counter(row["data_quality_grade"] for row in audited)
    blocker_distribution: Counter[str] = Counter()
    fallback_field_distribution: Counter[str] = Counter()
    for row in audited:
        blocker_distribution.update(row.get("execution_truth_blockers") or [])
        fallback_field_distribution.update(row.get("fallback_fields") or [])
    dirty_selected = [row for row in audited if row["dirty_selected"]]
    summary = {
        "source": source,
        "total_candidates": len(candidates),
        "execution_truth_allowed": sum(1 for row in audited if row["execution_truth_allowed"]),
        "execution_truth_blocked": sum(1 for row in audited if not row["execution_truth_allowed"]),
        "selected_or_executable_hint": sum(1 for row in audited if row["selected_or_executable_hint"]),
        "dirty_selected_or_executable": len(dirty_selected),
        "fallback_candidate_count": sum(1 for row in audited if row.get("fallback_fields")),
    }
    return {
        "summary": summary,
        "grade_distribution": dict(grade_distribution),
        "blocker_distribution": blocker_distribution,
        "fallback_field_distribution": dict(fallback_field_distribution),
        "candidate_pool_counts": pool.counts,
        "dirty_selected_candidates": dirty_selected,
        "candidates": audited,
    }


def _resolve_input_path(args: argparse.Namespace) -> Path | None:
    if args.input:
        return Path(args.input)
    for raw in DEFAULT_INPUT_CANDIDATES:
        candidate = Path(raw)
        if candidate.exists():
            return candidate
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Non-wired Tradebot candidate truth validator")
    parser.add_argument("--input", help="Path to candidate/trade JSON file. If omitted, common queue/log paths are tried.")
    parser.add_argument("--out-json", default=str(logs_dir() / "candidate_truth_report.json"), help="Output JSON report path")
    parser.add_argument("--out-md", default=str(logs_dir() / "candidate_truth_report.md"), help="Output Markdown report path")
    parser.add_argument("--fail-on-dirty-selected", action="store_true", help="Exit non-zero if selected/executable dirty candidates are detected")
    parser.add_argument("--print-summary", action="store_true", help="Print summary to stdout")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = _resolve_input_path(args)
    if input_path is None:
        print("No input file found. Pass --input or create one of the default review/log files.", file=sys.stderr)
        return 2
    if not input_path.exists():
        print(f"Input file does not exist: {input_path}", file=sys.stderr)
        return 2

    payload = _load_json(input_path)
    candidates = _extract_candidates(payload)
    report = build_truth_report(candidates, source=str(input_path))
    _write_json(Path(args.out_json), report)
    _write_markdown(Path(args.out_md), report)

    if args.print_summary:
        print(json.dumps(report["summary"], indent=2, sort_keys=True))

    dirty_count = int(report["summary"].get("dirty_selected_or_executable", 0) or 0)
    if args.fail_on_dirty_selected and dirty_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
