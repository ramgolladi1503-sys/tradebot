#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.shadow_truth import shadow_evaluate_candidates
from scripts.build_opportunity_truth_report import DEFAULT_SOURCES, _merge_candidates_by_key
from core.paths import logs_dir


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Shadow Truth Audit Report")
    lines.append("")
    lines.append("This report is shadow-only. It does not change execution, selection, allocation, queues, or dashboard runtime behavior.")
    lines.append("")
    lines.append("## Safety")
    lines.append("")
    lines.append(f"- **mode**: {payload.get('mode')}")
    lines.append(f"- **behavior_changed**: {payload.get('behavior_changed')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **total_candidates**: {payload.get('total_candidates')}")
    lines.append("")
    lines.append("## Severity Counts")
    lines.append("")
    for severity, count in sorted((payload.get("severity_counts") or {}).items()):
        lines.append(f"- {severity}: {count}")
    lines.append("")
    lines.append("## Drift Counts")
    lines.append("")
    for drift, count in sorted((payload.get("drift_counts") or {}).items()):
        lines.append(f"- {drift}: {count}")
    lines.append("")
    lines.append("## Critical Drifts")
    lines.append("")
    critical = payload.get("critical_drifts") or []
    if not critical:
        lines.append("No critical drifts detected.")
    else:
        for row in critical:
            blockers = ", ".join(row.get("shadow_blockers") or []) or "none"
            lines.append(f"- `{row.get('ref')}` symbol={row.get('symbol')} grade={row.get('shadow_data_quality_grade')} blockers={blockers} action={row.get('recommended_action')}")
    lines.append("")
    lines.append("## High Drifts")
    lines.append("")
    high = payload.get("high_drifts") or []
    if not high:
        lines.append("No high drifts detected.")
    else:
        for row in high:
            blockers = ", ".join(row.get("shadow_blockers") or []) or "none"
            lines.append(f"- `{row.get('ref')}` symbol={row.get('symbol')} grade={row.get('shadow_data_quality_grade')} blockers={blockers} action={row.get('recommended_action')}")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run non-invasive shadow truth audit")
    parser.add_argument("--inputs", nargs="*", default=None, help="Input JSON files. Defaults to common logs/runtime files.")
    parser.add_argument("--out-json", default=str(logs_dir() / "shadow_truth_audit.json"))
    parser.add_argument("--out-md", default=str(logs_dir() / "shadow_truth_audit.md"))
    parser.add_argument("--fail-on-critical", action="store_true", help="Exit non-zero if critical shadow drifts are detected")
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sources = [Path(raw) for raw in (args.inputs if args.inputs else DEFAULT_SOURCES)]
    candidates, loaded_sources = _merge_candidates_by_key(sources)
    payload = shadow_evaluate_candidates(candidates)
    payload["loaded_sources"] = loaded_sources
    _write_json(Path(args.out_json), payload)
    _write_markdown(Path(args.out_md), payload)
    if args.print_summary:
        print(json.dumps({
            "mode": payload.get("mode"),
            "behavior_changed": payload.get("behavior_changed"),
            "total_candidates": payload.get("total_candidates"),
            "severity_counts": payload.get("severity_counts"),
            "drift_counts": payload.get("drift_counts"),
        }, indent=2, sort_keys=True))
    critical_count = len(payload.get("critical_drifts") or [])
    return 1 if args.fail_on_critical and critical_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
