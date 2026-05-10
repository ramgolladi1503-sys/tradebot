#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_REPORTS = {
    "candidate_truth": "logs/candidate_truth_report.json",
    "opportunity_truth": "logs/opportunity_truth_report.json",
    "shadow_truth": "logs/shadow_truth_audit.json",
}


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def _candidate_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {"exists": False}
    summary = dict(payload.get("summary") or {})
    return {
        "exists": True,
        "total_candidates": summary.get("total_candidates"),
        "dirty_selected_or_executable": summary.get("dirty_selected_or_executable"),
        "fallback_candidate_count": summary.get("fallback_candidate_count"),
        "execution_truth_allowed": summary.get("execution_truth_allowed"),
        "execution_truth_blocked": summary.get("execution_truth_blocked"),
    }


def _opportunity_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {"exists": False}
    truth_report = payload.get("truth_report") if isinstance(payload.get("truth_report"), dict) else {}
    summary = dict(truth_report.get("summary") or {})
    return {
        "exists": True,
        "candidate_count_after_merge": payload.get("candidate_count_after_merge"),
        "dirty_selected_or_executable": summary.get("dirty_selected_or_executable"),
        "fallback_candidate_count": summary.get("fallback_candidate_count"),
        "execution_truth_allowed": summary.get("execution_truth_allowed"),
        "execution_truth_blocked": summary.get("execution_truth_blocked"),
    }


def _shadow_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {"exists": False}
    severity_counts = dict(payload.get("severity_counts") or {})
    drift_counts = dict(payload.get("drift_counts") or {})
    return {
        "exists": True,
        "mode": payload.get("mode"),
        "behavior_changed": payload.get("behavior_changed"),
        "total_candidates": payload.get("total_candidates"),
        "critical": severity_counts.get("CRITICAL", 0),
        "high": severity_counts.get("HIGH", 0),
        "low": severity_counts.get("LOW", 0),
        "info": severity_counts.get("INFO", 0),
        "current_allows_shadow_blocks": drift_counts.get("CURRENT_ALLOWS_SHADOW_BLOCKS", 0),
        "execution_allowed_shadow_blocks": drift_counts.get("EXECUTION_ALLOWED_SHADOW_BLOCKS", 0),
        "selected_shadow_blocks": drift_counts.get("SELECTED_SHADOW_BLOCKS", 0),
    }


def build_summary(paths: dict[str, Path]) -> dict[str, Any]:
    candidate = _candidate_summary(_load_json(paths["candidate_truth"]))
    opportunity = _opportunity_summary(_load_json(paths["opportunity_truth"]))
    shadow = _shadow_summary(_load_json(paths["shadow_truth"]))
    merge_blockers: list[str] = []
    if candidate.get("dirty_selected_or_executable", 0) not in (None, 0):
        merge_blockers.append("candidate_truth_dirty_selected")
    if opportunity.get("dirty_selected_or_executable", 0) not in (None, 0):
        merge_blockers.append("opportunity_truth_dirty_selected")
    if shadow.get("critical", 0) not in (None, 0):
        merge_blockers.append("shadow_critical_drift")
    if shadow.get("high", 0) not in (None, 0):
        merge_blockers.append("shadow_high_drift")
    return {
        "candidate_truth": candidate,
        "opportunity_truth": opportunity,
        "shadow_truth": shadow,
        "merge_blocked": bool(merge_blockers),
        "merge_blockers": merge_blockers,
    }


def _print_human(summary: dict[str, Any]) -> None:
    print("Truth Report Summary")
    print("====================")
    print(f"merge_blocked: {summary['merge_blocked']}")
    print(f"merge_blockers: {', '.join(summary['merge_blockers']) if summary['merge_blockers'] else 'none'}")
    print("")
    for section in ("candidate_truth", "opportunity_truth", "shadow_truth"):
        print(section)
        print("-" * len(section))
        payload = summary.get(section) or {}
        for key, value in payload.items():
            print(f"{key}: {value}")
        print("")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize non-wired truth reports")
    parser.add_argument("--candidate-truth", default=DEFAULT_REPORTS["candidate_truth"])
    parser.add_argument("--opportunity-truth", default=DEFAULT_REPORTS["opportunity_truth"])
    parser.add_argument("--shadow-truth", default=DEFAULT_REPORTS["shadow_truth"])
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human summary")
    parser.add_argument("--fail-if-blocked", action="store_true", help="Exit non-zero if merge blockers are present")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = build_summary(
        {
            "candidate_truth": Path(args.candidate_truth),
            "opportunity_truth": Path(args.opportunity_truth),
            "shadow_truth": Path(args.shadow_truth),
        }
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_human(summary)
    return 1 if args.fail_if_blocked and summary["merge_blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
